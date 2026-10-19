"""Доступ тренеров: приглашения от админа и от других тренеров, профиль и его настройка.

Доступ живёт в базе: строка в trainers с is_active=True. Админы (ADMIN_TELEGRAM_IDS)
становятся тренерами автоматически и выдают доступ другим одноразовыми ссылками. Каждый
тренер может пригласить коллегу своей постоянной личной ссылкой: пригласивший запоминается
в referred_by_id.
"""

import secrets
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.db.models import Trainer, TrainerInvite, User
from trenio.delivery.kick import kick
from trenio.services import notifications, subscription

# Префикс параметра /start в ссылке-приглашении тренера: t.me/бот?start=tr_<код>
TRAINER_INVITE_PREFIX = "tr_"
# Личная ссылка тренера для коллег: t.me/бот?start=r_<код>
REFERRAL_PREFIX = "r_"


class InviteError(StrEnum):
    NOT_FOUND = "not_found"
    EXPIRED = "expired"
    USED = "used"
    # Доступ этого человека отключил админ: чужая ссылка его не возвращает
    DISABLED = "disabled"


class InviteRejected(Exception):
    def __init__(self, reason: InviteError) -> None:
        super().__init__(reason)
        self.reason = reason


class InvalidTimezone(ValueError):
    pass


def is_admin(user: User, admin_telegram_ids: Collection[int]) -> bool:
    return user.telegram_id is not None and user.telegram_id in admin_telegram_ids


def _new_code() -> str:
    # 16 байт = 22 символа [A-Za-z0-9_-]: подходит для параметра start и не угадывается
    return secrets.token_urlsafe(16)


def _full_name(user: User) -> str:
    return " ".join(part for part in (user.first_name, user.last_name) if part)


def validate_timezone(name: str) -> str:
    # Только имена IANA вида "Europe/Moscow": ZoneInfo понимает и "UTC", и пути к файлам
    if "/" not in name or name.startswith("/") or ".." in name:
        raise InvalidTimezone(name)
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise InvalidTimezone(name) from None
    return name


async def get_trainer(session: AsyncSession, user_id: int) -> Trainer | None:
    return await session.scalar(select(Trainer).where(Trainer.user_id == user_id))


async def get_active_trainer(session: AsyncSession, user_id: int) -> Trainer | None:
    return await session.scalar(
        select(Trainer).where(Trainer.user_id == user_id, Trainer.is_active.is_(True))
    )


async def grant_trainer(
    session: AsyncSession, user: User, referred_by: Trainer | None = None
) -> Trainer:
    """Делает пользователя тренером или возвращает доступ отключённому. Коммит за вызывающим."""
    stmt = (
        insert(Trainer)
        .values(
            user_id=user.id,
            display_name=_full_name(user),
            invite_code=_new_code(),
            referral_code=_new_code(),
            referred_by_id=referred_by.id if referred_by is not None else None,
            trial_until=subscription.trial_until(datetime.now(UTC)),
        )
        # Повторная выдача только включает доступ: профиль, ссылки и подписка сохраняются
        .on_conflict_do_update(
            index_elements=[Trainer.user_id],
            set_={"is_active": True, "updated_at": func.now()},
        )
        .returning(Trainer)
        .execution_options(populate_existing=True)
    )
    return (await session.scalars(stmt)).one()


async def ensure_admin_is_trainer(
    session: AsyncSession, user: User, admin_telegram_ids: Collection[int]
) -> Trainer | None:
    """Админ всегда тренер: профиль создаётся при первом входе без всяких приглашений."""
    if not is_admin(user, admin_telegram_ids):
        return await get_active_trainer(session, user.id)
    trainer = await get_active_trainer(session, user.id)
    if trainer is None:
        trainer = await grant_trainer(session, user)
        await session.commit()
    return trainer


async def create_invite(session: AsyncSession, admin: User, ttl: timedelta) -> TrainerInvite:
    invite = TrainerInvite(
        code=_new_code(), created_by_id=admin.id, expires_at=datetime.now(UTC) + ttl
    )
    session.add(invite)
    await session.commit()
    return invite


async def accept_invite(session: AsyncSession, user: User, code: str) -> Trainer:
    """Погашает приглашение и выдаёт доступ тренера. Одна ссылка — один тренер."""
    try:
        return await _accept_invite(session, user, code)
    except InviteRejected:
        # Завершаем транзакцию, чтобы снять блокировку строки. Изменений в ней нет, а commit,
        # в отличие от rollback, не сбрасывает загруженные объекты (expire_on_commit=False)
        await session.commit()
        raise


async def _accept_invite(session: AsyncSession, user: User, code: str) -> Trainer:
    # Блокировка строки: две одновременные попытки по одной ссылке не пройдут обе
    invite = await session.scalar(
        select(TrainerInvite).where(TrainerInvite.code == code).with_for_update()
    )
    if invite is None:
        raise InviteRejected(InviteError.NOT_FOUND)
    if invite.used_by_id is not None:
        # Повторное открытие своей же ссылки не ошибка
        if invite.used_by_id == user.id:
            trainer = await get_active_trainer(session, user.id)
            if trainer is not None:
                await session.commit()
                return trainer
        raise InviteRejected(InviteError.USED)
    if invite.expires_at <= datetime.now(UTC):
        raise InviteRejected(InviteError.EXPIRED)

    existing = await get_active_trainer(session, user.id)
    if existing is not None:
        # Уже тренер: ссылку не тратим, её можно отдать другому человеку
        await session.commit()
        return existing
    trainer = await grant_trainer(session, user)
    invite.used_by_id = user.id
    invite.used_at = datetime.now(UTC)
    await session.commit()
    return trainer


def referral_link(bot_username: str, trainer: Trainer) -> str:
    return f"https://t.me/{bot_username}?start={REFERRAL_PREFIX}{trainer.referral_code}"


async def accept_referral(session: AsyncSession, user: User, code: str) -> Trainer:
    """Выдаёт доступ тренера по личной ссылке коллеги. Ссылка многоразовая и бессрочная.

    Возвращает профиль нового тренера. Кто уже тренер, остаётся как был: пригласившим
    засчитывается только тот, по чьей ссылке человек пришёл впервые.
    """
    existing = await get_trainer(session, user.id)
    if existing is not None:
        if not existing.is_active:
            raise InviteRejected(InviteError.DISABLED)
        return existing
    inviter = await session.scalar(
        select(Trainer).where(Trainer.referral_code == code, Trainer.is_active.is_(True))
    )
    if inviter is None:
        raise InviteRejected(InviteError.NOT_FOUND)
    trainer = await grant_trainer(session, user, referred_by=inviter)
    await notifications.trainer_joined(session, inviter, trainer, datetime.now(UTC))
    await session.commit()
    kick()
    return trainer


async def list_referrals(session: AsyncSession, trainer: Trainer) -> Sequence[Trainer]:
    """Тренеры, пришедшие по ссылке этого тренера, от новых к старым."""
    return (
        await session.scalars(
            select(Trainer)
            .where(Trainer.referred_by_id == trainer.id)
            .order_by(Trainer.created_at.desc(), Trainer.id.desc())
        )
    ).all()


async def list_trainers(session: AsyncSession) -> Sequence[Trainer]:
    return (await session.scalars(select(Trainer).order_by(Trainer.id))).all()


async def get_trainer_by_id(session: AsyncSession, trainer_id: int) -> Trainer | None:
    return await session.get(Trainer, trainer_id)


async def set_trainer_active(
    session: AsyncSession, trainer_id: int, active: bool
) -> Trainer | None:
    trainer = await get_trainer_by_id(session, trainer_id)
    if trainer is None:
        return None
    trainer.is_active = active
    await session.commit()
    return trainer


@dataclass(frozen=True, slots=True)
class TrainerProfileUpdate:
    """Поля, которые тренер меняет сам. None — поле не трогаем."""

    display_name: str | None = None
    timezone: str | None = None
    address: str | None = None
    auto_confirm: bool | None = None
    cancel_hours: int | None = None
    slot_step_min: int | None = None
    one_off_mode: str | None = None
    # Пустая строка убирает правила
    rules: str | None = None


async def update_profile(
    session: AsyncSession, trainer: Trainer, changes: TrainerProfileUpdate
) -> Trainer:
    if changes.timezone is not None:
        trainer.timezone = validate_timezone(changes.timezone)
    if changes.display_name is not None:
        trainer.display_name = changes.display_name
    if changes.address is not None:
        # Пустая строка очищает адрес
        trainer.address = changes.address or None
    if changes.auto_confirm is not None:
        trainer.auto_confirm = changes.auto_confirm
    if changes.cancel_hours is not None:
        trainer.cancel_hours = changes.cancel_hours
    if changes.slot_step_min is not None:
        trainer.slot_step_min = changes.slot_step_min
    if changes.one_off_mode is not None:
        trainer.one_off_mode = changes.one_off_mode
    if changes.rules is not None and (changes.rules or None) != trainer.rules:
        # Новая редакция: клиенты подтвердят её при следующем открытии
        trainer.rules = changes.rules or None
        trainer.rules_updated_at = datetime.now(UTC)
    if trainer.onboarded_at is None:
        # Первое сохранение профиля и есть завершение онбординга
        trainer.onboarded_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(trainer)
    return trainer
