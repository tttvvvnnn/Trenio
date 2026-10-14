"""Тексты уведомлений. Собираются при отправке из свежих данных.

None вместо сообщения — уведомление больше не нужно: запись отменили, занятие началось.
Время пишем по часовому поясу тренера, как в Mini App. Текст без разметки: в именах
и адресах может быть что угодно.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.bot.callbacks import Action, BookingAction
from trenio.config import get_settings
from trenio.db.models import ACTIVE_BOOKING_STATUSES, Booking, Notification, Package, User
from trenio.delivery.channel import Button, OutMessage
from trenio.services.bookings import client_can_cancel
from trenio.services.notifications import Kind, Role, Status
from trenio.services.packages import due, left

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


def action(text: str, act: Action, booking: Booking) -> Button:
    return Button(text, callback_data=BookingAction(action=act, booking_id=booking.id).pack())


def client_cancel(booking: Booking, now: datetime) -> list[list[Button]]:
    # Кнопку показываем, только пока клиент может отменить сам
    if not client_can_cancel(booking, now):
        return []
    return [[action("Отменить запись", Action.CANCEL, booking)]]


def rubles(amount: int) -> str:
    return f"{amount:,}".replace(",", "\u00a0") + "\u00a0₽"


def sessions_word(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return "занятие"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return "занятия"
    return "занятий"


def _lines(*lines: str | None) -> str:
    return "\n".join(line for line in lines if line)


def _session_line(booking: Booking) -> str:
    return f"{booking.service.name} · {when(booking.starts_at, booking.trainer.timezone)}"


def _comment(comment: str | None) -> str | None:
    return f"Комментарий: {comment}" if comment else None


def _confirm_buttons(booking: Booking) -> list[list[Button]]:
    return [
        [
            action("Подтвердить", Action.CONFIRM, booking),
            action("Отклонить", Action.DECLINE, booking),
        ]
    ]


def _rescheduled(booking: Booking, row: Notification, now: datetime) -> OutMessage | None:
    # Запись отменили или успели перенести ещё раз: о новом переносе придёт своё сообщение
    if booking.status not in ACTIVE_BOOKING_STATUSES:
        return None
    if datetime.fromisoformat(row.payload["to"]) != booking.starts_at:
        return None
    timezone = booking.trainer.timezone
    times = (
        f"Было: {when(datetime.fromisoformat(row.payload['from']), timezone)}",
        f"Стало: {when(booking.starts_at, timezone)}",
    )
    comment = _comment(booking.reschedule_comment)
    if Role(row.payload["by"]) is Role.CLIENT:
        pending = booking.status == "pending"
        text = _lines(
            f"🔁 {person(booking.client)} перенёс(ла) запись"
            + (", ждёт подтверждения" if pending else ""),
            booking.service.name,
            *times,
            comment,
        )
        if pending and booking.starts_at > now:
            return OutMessage(text, _confirm_buttons(booking) + open_app())
        return OutMessage(text, open_app())
    text = _lines(
        f"🔁 Тренер {booking.trainer.display_name} перенёс запись",
        booking.service.name,
        *times,
        address(booking),
        comment,
    )
    return OutMessage(text, client_cancel(booking, now) + open_app())


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
        return OutMessage(text, client_cancel(booking, now) + open_app())
    text = _lines(
        f"⏰ {soon.capitalize()}: {person(booking.client)}",
        booking.service.name,
    )
    return OutMessage(text, open_app())


def _attendance_prompt(booking: Booking) -> OutMessage | None:
    # Отметили в приложении раньше, чем пришла просьба, или запись отменили
    if booking.attendance is not None or booking.status not in ACTIVE_BOOKING_STATUSES:
        return None
    text = _lines(
        "Как прошло занятие?",
        f"{person(booking.client)}, {_session_line(booking)}",
    )
    buttons = [
        [action("Прошла", Action.ATTENDED, booking)],
        [
            action("Пропуск, списать", Action.MISSED_CHARGED, booking),
            action("Пропуск, не списывать", Action.MISSED_FREE, booking),
        ],
    ]
    return OutMessage(text, buttons)


async def _package_left(session: AsyncSession, row: Notification) -> OutMessage | None:
    package = await session.get(Package, row.package_id)
    expected = int(row.payload["left"])
    # Отметку успели снять или поставить ещё одну: это сообщение уже неверно
    if package is None or package.closed_at is not None or left(package) != expected:
        return None
    client = await session.get(User, package.client_id)
    assert client is not None
    name = f"«{package.name}»"
    debt = due(package)
    if Role(row.payload["role"]) is Role.CLIENT:
        if expected == 0:
            head = f"Блок {name} закончился. Договоритесь с тренером о новом"
        else:
            head = f"В блоке {name} осталось {expected} {sessions_word(expected)}"
        tail = f"Осталось доплатить {rubles(debt)}" if debt else None
    else:
        if expected == 0:
            head = f"У клиента {person(client)} закончился блок {name}"
        else:
            head = (
                f"У клиента {person(client)} в блоке {name} осталось "
                f"{expected} {sessions_word(expected)}"
            )
        tail = f"Долг по блоку: {rubles(debt)}" if debt else None
    return OutMessage(_lines(f"📦 {head}", tail), open_app())


async def render(session: AsyncSession, row: Notification, now: datetime) -> OutMessage | None:
    kind = Kind(row.kind)
    if kind is Kind.PACKAGE_LEFT:
        return await _package_left(session, row)
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
        case Kind.ATTENDANCE_PROMPT:
            return _attendance_prompt(booking)
        case Kind.PACKAGE_LEFT:
            return None
        case Kind.NEW_BOOKING:
            if not active:
                return None
            pending = booking.status == "pending"
            text = _lines(
                "🆕 Новая запись" + (", ждёт подтверждения" if pending else ""),
                client,
                _session_line(booking),
            )
            if pending and booking.starts_at > now:
                return OutMessage(text, _confirm_buttons(booking) + open_app())
        case Kind.TRAINER_BOOKED:
            if not active:
                return None
            text = _lines(
                f"📅 Тренер {trainer} записал вас на тренировку",
                _session_line(booking),
                address(booking),
            )
            return OutMessage(text, client_cancel(booking, now) + open_app())
        case Kind.BOOKING_CONFIRMED:
            if not active:
                return None
            text = _lines(
                f"✅ Тренер {trainer} подтвердил запись",
                _session_line(booking),
                address(booking),
            )
        case Kind.BOOKING_RESCHEDULED:
            return _rescheduled(booking, row, now)
        case Kind.BOOKING_DECLINED:
            text = _lines(
                f"Тренер {trainer} не сможет провести занятие в это время",
                _session_line(booking),
                _comment(booking.cancel_comment),
                "Выберите другое окошко в приложении.",
            )
        case Kind.CLIENT_CANCELLED:
            text = _lines(
                f"❌ {client} отменил(а) запись",
                _session_line(booking),
                _comment(booking.cancel_comment),
            )
        case Kind.TRAINER_CANCELLED:
            text = _lines(
                f"❌ Тренер {trainer} отменил запись",
                _session_line(booking),
                _comment(booking.cancel_comment),
            )
    return OutMessage(text, open_app())
