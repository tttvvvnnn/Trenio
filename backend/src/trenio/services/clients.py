"""Клиенты тренера: привязка по персональной ссылке и списки с обеих сторон.

Клиента без Telegram тренер заводит сам. Потом клиент открывает личную ссылку из его
карточки, и всё, что было у такой строки users, переезжает на его Telegram-аккаунт.
"""

import secrets
from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import and_, delete, exists, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from trenio.db.models import (
    ACTIVE_BOOKING_STATUSES,
    Booking,
    ClientMeasurement,
    Notification,
    Package,
    ReminderSetting,
    Trainer,
    TrainerClient,
    User,
)
from trenio.delivery.kick import kick
from trenio.services import notifications, subscription

# Префикс параметра /start в ссылке тренера для клиентов: t.me/бот?start=c_<код>
CLIENT_INVITE_PREFIX = "c_"
# Личная ссылка клиента без Telegram: t.me/бот?start=u_<код>
CLAIM_PREFIX = "u_"


class LinkError(StrEnum):
    NOT_FOUND = "not_found"
    OWN_LINK = "own_link"
    # Клиент уже привязан к Telegram или не был заведён тренером
    NOT_OFFLINE = "not_offline"
    # Склеить можно только с клиентом, у которого есть Telegram
    TARGET_OFFLINE = "target_offline"


class LinkRejected(Exception):
    def __init__(self, reason: LinkError) -> None:
        super().__init__(reason)
        self.reason = reason


def client_invite_link(bot_username: str, trainer: Trainer) -> str:
    return f"https://t.me/{bot_username}?start={CLIENT_INVITE_PREFIX}{trainer.invite_code}"


async def link_client(session: AsyncSession, user: User, invite_code: str) -> Trainer:
    """Делает пользователя клиентом тренера. Повторный переход по ссылке ничего не ломает."""
    trainer = await session.scalar(
        select(Trainer).where(Trainer.invite_code == invite_code, Trainer.is_active.is_(True))
    )
    if trainer is None:
        raise LinkRejected(LinkError.NOT_FOUND)
    if trainer.user_id == user.id:
        raise LinkRejected(LinkError.OWN_LINK)
    linked = await session.scalar(
        select(TrainerClient.id).where(
            TrainerClient.trainer_id == trainer.id, TrainerClient.user_id == user.id
        )
    )
    if linked is None:
        now = datetime.now(UTC)
        try:
            await subscription.ensure_client_slot(session, trainer, now)
        except subscription.ClientLimitReached:
            # Тренер узнает, что клиент не смог присоединиться, и сможет оформить Pro
            await notifications.client_limit(session, trainer, user, now)
            await session.commit()
            kick()
            raise
    await session.execute(
        insert(TrainerClient)
        .values(trainer_id=trainer.id, user_id=user.id)
        .on_conflict_do_nothing(constraint="uq_trainer_clients_pair")
    )
    await session.commit()
    return trainer


async def _offline_link(
    session: AsyncSession, trainer: Trainer, client_id: int, *, lock: bool = False
) -> TrainerClient:
    """Связь тренера с клиентом без Telegram, которого он сам и завёл."""
    stmt = (
        select(TrainerClient)
        .join(TrainerClient.user)
        .where(TrainerClient.trainer_id == trainer.id, TrainerClient.user_id == client_id)
    )
    if lock:
        stmt = stmt.with_for_update(of=TrainerClient)
    link = await session.scalar(stmt)
    if link is None:
        raise LinkRejected(LinkError.NOT_FOUND)
    if not link.user.is_offline or link.user.created_by_trainer_id != trainer.id:
        raise LinkRejected(LinkError.NOT_OFFLINE)
    return link


async def create_offline_client(
    session: AsyncSession,
    trainer: Trainer,
    first_name: str,
    last_name: str | None,
    notes: str | None,
) -> TrainerClient:
    """Клиент, который не пользуется ботом: тренер записывает его и ведёт блоки сам."""
    await subscription.ensure_client_slot(session, trainer, datetime.now(UTC))
    user = User(
        first_name=first_name,
        last_name=last_name,
        name_custom=True,
        avatar_mode="none",
        created_by_trainer_id=trainer.id,
    )
    session.add(user)
    await session.flush()
    link = TrainerClient(trainer_id=trainer.id, user_id=user.id, notes=notes)
    session.add(link)
    await session.commit()
    return await _offline_link(session, trainer, user.id)


async def rename_offline_client(
    session: AsyncSession, trainer: Trainer, client_id: int, first_name: str, last_name: str | None
) -> TrainerClient:
    link = await _offline_link(session, trainer, client_id)
    link.user.first_name = first_name
    link.user.last_name = last_name
    await session.commit()
    return link


def claim_link(bot_username: str, code: str) -> str:
    return f"https://t.me/{bot_username}?start={CLAIM_PREFIX}{code}"


async def claim_code(session: AsyncSession, trainer: Trainer, client_id: int) -> str:
    """Код личной ссылки клиента без Telegram. Один на клиента, пока он не привяжется."""
    link = await _offline_link(session, trainer, client_id, lock=True)
    if link.claim_code is None:
        link.claim_code = secrets.token_urlsafe(12)
    code = link.claim_code
    await session.commit()
    return code


async def claim(session: AsyncSession, user: User, code: str, now: datetime) -> Trainer:
    """Человек открыл личную ссылку: клиент без Telegram становится его аккаунтом."""
    link = await session.scalar(
        select(TrainerClient)
        .where(TrainerClient.claim_code == code)
        .with_for_update(of=TrainerClient)
    )
    if link is None or not link.trainer.is_active:
        raise LinkRejected(LinkError.NOT_FOUND)
    if link.trainer.user_id == user.id:
        raise LinkRejected(LinkError.OWN_LINK)
    trainer = link.trainer
    await merge_clients(session, link.user, user, now)
    await session.commit()
    return trainer


async def merge_offline_client(
    session: AsyncSession, trainer: Trainer, client_id: int, into_id: int, now: datetime
) -> None:
    """Тренер говорит: клиент без Telegram и этот клиент с Telegram — один человек."""
    link = await _offline_link(session, trainer, client_id, lock=True)
    target = await session.scalar(
        select(User)
        .join(TrainerClient, TrainerClient.user_id == User.id)
        .where(TrainerClient.trainer_id == trainer.id, User.id == into_id)
    )
    if target is None:
        raise LinkRejected(LinkError.NOT_FOUND)
    if target.is_offline:
        raise LinkRejected(LinkError.TARGET_OFFLINE)
    await merge_clients(session, link.user, target, now)
    await session.commit()


async def merge_clients(session: AsyncSession, source: User, target: User, now: datetime) -> None:
    """Переносит всё клиента без Telegram на аккаунт target и удаляет source.

    Остаётся имя target: то, что человек выбрал сам. Коммит — за вызывающим.
    """
    if not source.is_offline or source.created_by_trainer_id is None:
        raise LinkRejected(LinkError.NOT_OFFLINE)
    assert source.id != target.id

    # Связи с тренерами. Если человек уже клиент этого тренера (зашёл по общей ссылке),
    # оставляем его связь и дописываем к ней заметки
    for link in (
        await session.scalars(select(TrainerClient).where(TrainerClient.user_id == source.id))
    ).all():
        existing = await session.scalar(
            select(TrainerClient).where(
                TrainerClient.trainer_id == link.trainer_id, TrainerClient.user_id == target.id
            )
        )
        if existing is None:
            link.user_id = target.id
            link.claim_code = None
            continue
        notes = [n for n in (existing.notes, link.notes) if n]
        existing.notes = "\n\n".join(notes) or None
        # Замеры тоже переходят к оставшейся связи, иначе уйдут каскадом вместе с этой
        await session.execute(
            update(ClientMeasurement)
            .where(ClientMeasurement.trainer_client_id == link.id)
            .values(trainer_client_id=existing.id)
        )
        await session.delete(link)
    await session.flush()

    # Одна и та же запись у обоих аккаунтов (тренер успел записать обоих) — оставляем одну
    theirs = aliased(Booking)
    await session.execute(
        update(Booking)
        .where(
            Booking.client_id == source.id,
            Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            exists().where(
                and_(
                    theirs.client_id == target.id,
                    theirs.service_id == Booking.service_id,
                    theirs.starts_at == Booking.starts_at,
                    theirs.status.in_(ACTIVE_BOOKING_STATUSES),
                )
            ),
        )
        .values(status="cancelled", cancelled_by="trainer", cancelled_at=now)
    )
    moved = (
        await session.scalars(
            update(Booking)
            .where(Booking.client_id == source.id)
            .values(client_id=target.id)
            .returning(Booking.id)
        )
    ).all()
    await session.execute(
        update(Package).where(Package.client_id == source.id).values(client_id=target.id)
    )

    # Неотправленные сообщения клиенту без Telegram никому не нужны; напоминания
    # о будущих занятиях ставим заново — уже по настройкам самого человека
    await session.execute(
        delete(Notification).where(
            Notification.user_id == source.id, Notification.status == notifications.Status.PENDING
        )
    )
    await session.execute(
        update(Notification).where(Notification.user_id == source.id).values(user_id=target.id)
    )
    await session.execute(delete(ReminderSetting).where(ReminderSetting.user_id == source.id))
    await session.delete(source)
    await session.flush()

    if moved:
        upcoming = (
            await session.scalars(
                select(Booking).where(
                    Booking.id.in_(moved), Booking.status == "confirmed", Booking.starts_at > now
                )
            )
        ).all()
        for booking in upcoming:
            await notifications.schedule_reminders(
                session, booking, now, roles=(notifications.Role.CLIENT,)
            )


async def list_clients(session: AsyncSession, trainer: Trainer) -> Sequence[TrainerClient]:
    stmt = (
        select(TrainerClient)
        .join(TrainerClient.user)
        .where(TrainerClient.trainer_id == trainer.id)
        .order_by(User.first_name, User.last_name, TrainerClient.id)
    )
    return (await session.scalars(stmt)).all()


async def is_client(session: AsyncSession, trainer: Trainer, user_id: int) -> bool:
    found = await session.scalar(
        select(TrainerClient.id).where(
            TrainerClient.trainer_id == trainer.id, TrainerClient.user_id == user_id
        )
    )
    return found is not None


async def list_my_trainers(session: AsyncSession, user: User) -> Sequence[Trainer]:
    """Тренеры, к которым пользователь может записаться. Отключённых не показываем."""
    stmt = (
        select(Trainer)
        .join(TrainerClient, TrainerClient.trainer_id == Trainer.id)
        .where(TrainerClient.user_id == user.id, Trainer.is_active.is_(True))
        .order_by(Trainer.display_name, Trainer.id)
    )
    return (await session.scalars(stmt)).all()


async def list_my_links(session: AsyncSession, user: User) -> Sequence[TrainerClient]:
    """Связи клиента с тренерами — вместе с тем, принял ли он их правила."""
    stmt = (
        select(TrainerClient)
        .join(TrainerClient.trainer)
        .where(TrainerClient.user_id == user.id, Trainer.is_active.is_(True))
        .order_by(Trainer.display_name, Trainer.id)
    )
    return (await session.scalars(stmt)).all()


async def get_my_link(session: AsyncSession, user: User, trainer_id: int) -> TrainerClient | None:
    stmt = (
        select(TrainerClient)
        .join(TrainerClient.trainer)
        .where(
            TrainerClient.trainer_id == trainer_id,
            TrainerClient.user_id == user.id,
            Trainer.is_active.is_(True),
        )
    )
    return await session.scalar(stmt)


async def accept_rules(session: AsyncSession, link: TrainerClient, now: datetime) -> None:
    link.rules_accepted_at = now
    await session.commit()


async def get_my_trainer(session: AsyncSession, user: User, trainer_id: int) -> Trainer | None:
    stmt = (
        select(Trainer)
        .join(TrainerClient, TrainerClient.trainer_id == Trainer.id)
        .where(
            Trainer.id == trainer_id,
            TrainerClient.user_id == user.id,
            Trainer.is_active.is_(True),
        )
    )
    return await session.scalar(stmt)
