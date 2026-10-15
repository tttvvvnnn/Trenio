"""Персональные данные: согласие с политикой, телефон клиента, удаление аккаунта.

Удаление аккаунта клиента обезличивает его, а не стирает: записи, блоки и оплаты
остаются у тренеров, иначе поедут их финансы. Аккаунт тренера удаляется вместе со всем,
что тренер вёл: услугами, расписанием, записями, блоками и клиентами без Telegram.
"""

import re
from datetime import datetime
from enum import StrEnum

from sqlalchemy import delete, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.db.models import (
    ACTIVE_BOOKING_STATUSES,
    Booking,
    Notification,
    Package,
    ReminderSetting,
    Trainer,
    TrainerClient,
    User,
)
from trenio.delivery.kick import kick
from trenio.services import avatars, notifications, progress

# Версия политики. Поменялся смысл текста — поднимаем, и согласие спросят у всех заново
POLICY_VERSION = 1

DELETED_NAME = "Удалённый клиент"
DELETED_COMMENT = "Клиент удалил аккаунт"

# Абзацы — одной строкой: Mini App и Telegram сами переносят их по ширине экрана
_POLICY = "\n".join(
    [
        "Политика обработки персональных данных Trenio",
        "",
        "Оператор: {operator}.",
        "Вопросы и запросы о ваших данных: {contact}.",
        "",
        "Какие данные мы обрабатываем",
        "• Из Telegram: ID, имя, фамилия, username, фото профиля.",
        "• Имя и фото, которые вы указали сами.",
        "• Записи на занятия, блоки, оплаты и отметки о посещении.",
        "• Заметки тренера о клиенте и о занятиях, замеры, которые записал тренер (вес, обхваты).",
        "• Телефон клиента, если тренер указал его с согласия клиента.",
        "",
        "Зачем",
        "Только чтобы работала запись к тренеру: расписание, напоминания, учёт блоков и оплат. "
        "Рекламу не показываем, данные не продаём.",
        "",
        "Кто их видит",
        "Ваш тренер видит ваши записи, блоки, оплаты и то, что записал о вас сам. "
        "Клиент видит только свои записи, блоки и замеры. Третьим лицам данные не передаются. "
        "Сообщения доставляются через Telegram.",
        "",
        "Где и сколько хранятся",
        "На сервере в России, пока у вас есть аккаунт. Резервные копии базы доступны только "
        "оператору.",
        "",
        "Ваши права",
        "Вы можете узнать, какие данные о вас хранятся, исправить их, удалить телефон или удалить "
        "аккаунт целиком в разделе «Профиль». При удалении аккаунта клиента его записи и оплаты "
        "остаются у тренера обезличенными, под именем «{deleted}», чтобы не ломать учёт тренера. "
        "Аккаунт тренера удаляется вместе с его расписанием, записями и блоками.",
        "",
        "Отзыв согласия равносилен удалению аккаунта: без данных сервис работать не может.",
    ]
)


def policy_text(operator: str, contact: str) -> str:
    return _POLICY.format(
        operator=operator.strip() or "владелец сервиса Trenio",
        contact=contact.strip() or "напишите боту Trenio",
        deleted=DELETED_NAME,
    )


def consent_required(user: User) -> bool:
    return user.consent_version is None or user.consent_version < POLICY_VERSION


async def give_consent(session: AsyncSession, user: User, now: datetime) -> None:
    user.consent_at = now
    user.consent_version = POLICY_VERSION
    await session.commit()


# --- Телефон клиента ---


class PhoneError(StrEnum):
    INVALID = "invalid"
    NO_CONSENT = "no_consent"
    NOT_FOUND = "not_found"


class PhoneRejected(Exception):
    def __init__(self, reason: PhoneError) -> None:
        super().__init__(reason.value)
        self.reason = reason


def normalize_phone(raw: str) -> str:
    """«8 (912) 345-67-89» → «+79123456789». Российские 8 и 7 приводим к +7."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits[0] == "8":
        digits = "7" + digits[1:]
    elif len(digits) == 10 and digits[0] == "9":
        digits = "7" + digits
    if not 10 <= len(digits) <= 15:
        raise PhoneRejected(PhoneError.INVALID)
    return "+" + digits


async def _trainer_link(session: AsyncSession, trainer: Trainer, client_id: int) -> TrainerClient:
    link = await session.scalar(
        select(TrainerClient).where(
            TrainerClient.trainer_id == trainer.id, TrainerClient.user_id == client_id
        )
    )
    if link is None or link.user.is_deleted:
        raise PhoneRejected(PhoneError.NOT_FOUND)
    return link


async def set_client_phone(
    session: AsyncSession,
    trainer: Trainer,
    client_id: int,
    phone: str | None,
    consent: bool,
    now: datetime,
) -> TrainerClient:
    """Тренер записывает телефон клиента. Без отметки о согласии клиента не сохраняем."""
    link = await _trainer_link(session, trainer, client_id)
    if phone is None:
        link.phone = None
        link.phone_consent_at = None
    else:
        if not consent:
            raise PhoneRejected(PhoneError.NO_CONSENT)
        link.phone = normalize_phone(phone)
        link.phone_consent_at = now
    await session.commit()
    return link


async def remove_my_phone(session: AsyncSession, user: User, trainer_id: int) -> None:
    """Клиент сам удаляет свой телефон у тренера."""
    link = await session.scalar(
        select(TrainerClient).where(
            TrainerClient.trainer_id == trainer_id, TrainerClient.user_id == user.id
        )
    )
    if link is None:
        raise PhoneRejected(PhoneError.NOT_FOUND)
    link.phone = None
    link.phone_consent_at = None
    await session.commit()


# --- Удаление аккаунта ---


async def _delete_trainer(session: AsyncSession, trainer: Trainer) -> None:
    # Клиенты без Telegram существуют только у этого тренера: уходят вместе с ним
    await session.execute(
        delete(User).where(User.created_by_trainer_id == trainer.id, User.telegram_id.is_(None))
    )
    # Остальное (услуги, расписание, записи, блоки, связи с клиентами) — каскадом
    await session.execute(delete(Trainer).where(Trainer.id == trainer.id))


async def _cancel_upcoming(session: AsyncSession, user: User, now: datetime) -> None:
    """Будущие записи клиента отменяем, тренер получает обычное «клиент отменил»."""
    upcoming = (
        await session.scalars(
            select(Booking).where(
                Booking.client_id == user.id,
                Booking.status.in_(ACTIVE_BOOKING_STATUSES),
                Booking.starts_at > now,
            )
        )
    ).all()
    for booking in upcoming:
        booking.status = "cancelled"
        booking.cancelled_by = "client"
        booking.cancelled_at = now
        booking.cancel_comment = DELETED_COMMENT
        await notifications.booking_cancelled(session, booking, notifications.Role.CLIENT, now)


async def _has_records(session: AsyncSession, user: User) -> bool:
    """Остались ли у тренеров записи, блоки или связи с этим человеком."""
    found = await session.scalar(
        select(
            or_(
                exists().where(TrainerClient.user_id == user.id),
                exists().where(Booking.client_id == user.id),
                exists().where(Package.client_id == user.id),
            )
        )
    )
    return bool(found)


async def delete_account(session: AsyncSession, user: User, now: datetime) -> None:
    trainer = await session.scalar(select(Trainer).where(Trainer.user_id == user.id))
    if trainer is not None:
        await _delete_trainer(session, trainer)

    # Сообщения самому человеку больше не нужны: ни неотправленные, ни история
    await session.execute(delete(Notification).where(Notification.user_id == user.id))
    await session.execute(delete(ReminderSetting).where(ReminderSetting.user_id == user.id))
    await _cancel_upcoming(session, user, now)
    await progress.forget(session, user)

    for link in (
        await session.scalars(select(TrainerClient).where(TrainerClient.user_id == user.id))
    ).all():
        link.notes = None
        link.phone = None
        link.phone_consent_at = None
        link.claim_code = None

    await session.flush()
    if not await _has_records(session, user):
        await session.delete(user)
        await session.commit()
        kick()
        return

    await avatars.forget(session, user)
    user.avatar_mode = avatars.AvatarMode.NONE
    user.telegram_id = None
    user.first_name = DELETED_NAME
    user.last_name = None
    user.name_custom = True
    user.telegram_first_name = None
    user.telegram_last_name = None
    user.username = None
    user.language_code = None
    user.avatar_checked_at = None
    user.last_seen_at = None
    user.trainer_tour_at = None
    user.client_tour_at = None
    user.consent_at = None
    user.consent_version = None
    user.created_by_trainer_id = None
    user.deleted_at = now
    await session.commit()
    kick()
