"""Доступ тренеров: приглашения от админа, профиль и его настройка.

Бета-доступ живёт в базе: строка в trainers с is_active=True. Админы (ADMIN_TELEGRAM_IDS)
становятся тренерами автоматически и выдают доступ другим одноразовыми ссылками.
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

# Префикс параметра /start в ссылке-приглашении тренера: t.me/бот?start=tr_<код>
TRAINER_INVITE_PREFIX = "tr_"


class InviteError(StrEnum):
    NOT_FOUND = "not_found"
    EXPIRED = "expired"
    USED = "used"


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


async def grant_trainer(session: AsyncSession, user: User) -> Trainer:
    """Делает пользователя тренером или возвращает доступ отключённому. Коммит за вызывающим."""
    stmt = (
        insert(Trainer)
        .values(user_id=user.id, display_name=_full_name(user), invite_code=_new_code())
        # Повторная выдача только включает доступ: профиль и ссылка для клиентов сохраняются
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
