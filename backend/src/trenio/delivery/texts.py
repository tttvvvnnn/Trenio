"""Тексты уведомлений. Собираются при отправке из свежих данных.

None вместо сообщения — уведомление больше не нужно: запись отменили, занятие началось.
Время пишем по часовому поясу тренера, как в Mini App. Текст без разметки: в именах
и адресах может быть что угодно.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.config import get_settings
from trenio.db.models import ACTIVE_BOOKING_STATUSES, Booking, Notification, User
from trenio.delivery.channel import Button, OutMessage
from trenio.services.notifications import Kind, Role, Status

WEEKDAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
MONTHS = (
    "янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек",
)  # fmt: skip


def person(user: User) -> str:
    return " ".join(part for part in (user.first_name, user.last_name) if part)


def when(starts_at: datetime, timezone: str) -> str:
    """«пт, 17 окт, 10:00»."""
    local = starts_at.astimezone(ZoneInfo(timezone))
    return f"{WEEKDAYS[local.weekday()]}, {local.day} {MONTHS[local.month - 1]}, {local:%H:%M}"


def when_soon(starts_at: datetime, timezone: str, now: datetime) -> str:
    """«сегодня в 10:00», «завтра в 10:00» или «пт, 17 окт в 10:00»."""
    zone = ZoneInfo(timezone)
    local = starts_at.astimezone(zone)
    today = now.astimezone(zone).date()
    if local.date() == today:
        day = "сегодня"
    elif local.date() == today + timedelta(days=1):
        day = "завтра"
    else:
        day = f"{WEEKDAYS[local.weekday()]}, {local.day} {MONTHS[local.month - 1]}"
    return f"{day} в {local:%H:%M}"


def address(booking: Booking) -> str | None:
    return booking.service.address or booking.trainer.address


def open_app() -> list[list[Button]]:
    url = get_settings().webapp_url
    # Telegram принимает кнопку Mini App только с https-адресом
    if not url.startswith("https://"):
        return []
    return [[Button("Открыть Trenio", webapp_url=url)]]


def _lines(*lines: str | None) -> str:
    return "\n".join(line for line in lines if line)


def _session_line(booking: Booking) -> str:
    return f"{booking.service.name} · {when(booking.starts_at, booking.trainer.timezone)}"


async def _superseded(session: AsyncSession, row: Notification, now: datetime) -> bool:
    """Есть более позднее напоминание о том же занятии, которому тоже пора.

    Так бывает, если сервис лежал: вместо «за сутки» и «за 2 часа» подряд уйдёт одно.
    """
    later = await session.scalar(
        select(Notification.id).where(
            Notification.booking_id == row.booking_id,
            Notification.user_id == row.user_id,
            Notification.kind == Kind.REMINDER,
            Notification.status == Status.PENDING,
            Notification.send_at > row.send_at,
            Notification.send_at <= now,
        )
    )
    return later is not None


def _reminder(booking: Booking, role: Role, now: datetime) -> OutMessage | None:
    if booking.status != "confirmed" or booking.starts_at <= now:
        return None
    soon = when_soon(booking.starts_at, booking.trainer.timezone, now)
    if role is Role.CLIENT:
        text = _lines(
            f"⏰ Напоминание: {soon} тренировка",
            f"{booking.service.name}, тренер {booking.trainer.display_name}",
            address(booking),
        )
    else:
        text = _lines(
            f"⏰ {soon.capitalize()}: {person(booking.client)}",
            booking.service.name,
        )
    return OutMessage(text, open_app())


async def render(session: AsyncSession, row: Notification, now: datetime) -> OutMessage | None:
    kind = Kind(row.kind)
    booking = await session.get(Booking, row.booking_id) if row.booking_id is not None else None
    if booking is None:
        return None
    active = booking.status in ACTIVE_BOOKING_STATUSES
    trainer = booking.trainer.display_name
    client = person(booking.client)

    match kind:
        case Kind.REMINDER:
            if await _superseded(session, row, now):
                return None
            return _reminder(booking, Role(row.payload["role"]), now)
        case Kind.NEW_BOOKING:
            if not active:
                return None
            pending = booking.status == "pending"
            text = _lines(
                "🆕 Новая запись" + (", ждёт подтверждения" if pending else ""),
                client,
                _session_line(booking),
            )
        case Kind.TRAINER_BOOKED:
            if not active:
                return None
            text = _lines(
                f"📅 Тренер {trainer} записал вас на тренировку",
                _session_line(booking),
                address(booking),
            )
        case Kind.BOOKING_CONFIRMED:
            if not active:
                return None
            text = _lines(
                f"✅ Тренер {trainer} подтвердил запись",
                _session_line(booking),
                address(booking),
            )
        case Kind.BOOKING_DECLINED:
            text = _lines(
                f"Тренер {trainer} не сможет провести занятие в это время",
                _session_line(booking),
                "Выберите другое окошко в приложении.",
            )
        case Kind.CLIENT_CANCELLED:
            text = _lines(f"❌ {client} отменил(а) запись", _session_line(booking))
        case Kind.TRAINER_CANCELLED:
            text = _lines(f"❌ Тренер {trainer} отменил запись", _session_line(booking))
    return OutMessage(text, open_app())
