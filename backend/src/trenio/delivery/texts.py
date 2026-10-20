"""Тексты уведомлений. Собираются при отправке из свежих данных.

None вместо сообщения — уведомление больше не нужно: запись отменили, занятие началось.
Время пишем по часовому поясу тренера, как в Mini App. Текст без разметки: в именах
и адресах может быть что угодно.
"""

from datetime import date, datetime, timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.bot.callbacks import Action, BookingAction
from trenio.config import get_settings
from trenio.db.models import (
    ACTIVE_BOOKING_STATUSES,
    Booking,
    Broadcast,
    Notification,
    Package,
    SubscriptionPayment,
    Trainer,
    User,
)
from trenio.delivery.channel import Button, OutMessage
from trenio.services import subscription
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


def open_app(text: str = "Открыть Trenio", **target: str | int) -> list[list[Button]]:
    """Кнопка Mini App. target — куда сразу открыть: role и booking, client или tab."""
    url = get_settings().webapp_url
    # Telegram принимает кнопку Mini App только с https-адресом
    if not url.startswith("https://"):
        return []
    if target:
        url += ("&" if "?" in url else "?") + urlencode(target)
    return [[Button(text, webapp_url=url)]]


def open_booking(booking: Booking, role: Role) -> list[list[Button]]:
    """Сразу на экран записи: тренеру заявку или запись, клиенту его запись."""
    pending = role is Role.TRAINER and booking.status == "pending"
    text = "Открыть заявку" if pending else "Открыть запись"
    return open_app(text, role=role.value, booking=booking.id)


def open_client(client_id: int) -> list[list[Button]]:
    return open_app("Открыть клиента", role=Role.TRAINER.value, client=client_id)


def open_tab(text: str, tab: str) -> list[list[Button]]:
    """Вкладка клиента: book — записаться, sessions — мои занятия и блоки."""
    return open_app(text, role=Role.CLIENT.value, tab=tab)


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
        link = open_booking(booking, Role.TRAINER)
        if pending and booking.starts_at > now:
            return OutMessage(text, _confirm_buttons(booking) + link)
        return OutMessage(text, link)
    text = _lines(
        f"🔁 Тренер {booking.trainer.display_name} перенёс запись",
        booking.service.name,
        *times,
        address(booking),
        comment,
    )
    return OutMessage(text, client_cancel(booking, now) + open_booking(booking, Role.CLIENT))


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
        return OutMessage(text, client_cancel(booking, now) + open_booking(booking, Role.CLIENT))
    text = _lines(
        f"⏰ {soon.capitalize()}: {person(booking.client)}",
        booking.service.name,
    )
    return OutMessage(text, open_booking(booking, Role.TRAINER))


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
    role = Role(row.payload["role"])
    if role is Role.CLIENT:
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
    link = open_tab("Мои занятия", "sessions") if role is Role.CLIENT else open_client(client.id)
    return OutMessage(_lines(f"📦 {head}", tail), link)


def day_month(day: date) -> str:
    """«17 окт»."""
    return f"{day.day} {MONTHS[day.month - 1]}"


def in_days(days: int) -> str:
    """«завтра», «через 7 дней»."""
    if days == 1:
        return "завтра"
    if days % 10 == 1 and days % 100 != 11:
        word = "день"
    elif days % 10 in (2, 3, 4) and days % 100 not in (12, 13, 14):
        word = "дня"
    else:
        word = "дней"
    return f"через {days} {word}"


async def _package_expiring(
    session: AsyncSession, row: Notification, now: datetime
) -> OutMessage | None:
    package = await session.get(Package, row.package_id)
    # Блок закрыли, продлили или занятия кончились: предупреждение уже неверно
    if (
        package is None
        or package.closed_at is not None
        or package.valid_until is None
        or package.valid_until.isoformat() != row.payload["valid_until"]
        or left(package) <= 0
    ):
        return None
    today = now.astimezone(ZoneInfo(package.trainer.timezone)).date()
    days = (package.valid_until - today).days
    if days < 0:
        return None
    client = await session.get(User, package.client_id)
    assert client is not None
    name = f"«{package.name}»"
    rest = left(package)
    sessions = f"{rest} {sessions_word(rest)}"
    if days == 0:
        when_ends = "сегодня последний день"
    else:
        when_ends = f"кончается {in_days(days)}, {day_month(package.valid_until)}"
    debt = due(package)
    role = Role(row.payload["role"])
    if role is Role.CLIENT:
        head = f"Срок блока {name} {when_ends}, а в нём ещё {sessions}"
        body = "Успейте их пройти или договоритесь с тренером о продлении"
        tail = f"Осталось доплатить {rubles(debt)}" if debt else None
    else:
        head = f"У клиента {person(client)} срок блока {name} {when_ends}, осталось {sessions}"
        body = "Продлить срок можно в карточке блока"
        tail = f"Долг по блоку: {rubles(debt)}" if debt else None
    link = open_tab("Мои занятия", "sessions") if role is Role.CLIENT else open_client(client.id)
    return OutMessage(_lines(f"⏳ {head}", body, tail), link)


async def _trainer_joined(session: AsyncSession, row: Notification) -> OutMessage | None:
    joined = await session.get(Trainer, row.payload["trainer_id"])
    if joined is None:
        return None
    return OutMessage(
        _lines(
            f"🤝 По вашей ссылке в Trenio пришёл тренер {person(joined.user)}",
            "Список приглашённых — в Профиле, «Пригласить тренера»",
        ),
        open_app("Кто пришёл по ссылке", role=Role.TRAINER.value, tab="referrals"),
    )


def open_subscription(text: str = "Оформить Pro") -> list[list[Button]]:
    return open_app(text, role=Role.TRAINER.value, tab="subscription")


async def _subscription_ending(
    session: AsyncSession, row: Notification, now: datetime
) -> OutMessage | None:
    trainer = await session.scalar(select(Trainer).where(Trainer.user_id == row.user_id))
    # Тренер успел продлить Pro или его отключили: предупреждение уже неверно
    if (
        trainer is None
        or not trainer.is_active
        or subscription.is_admin_trainer(trainer)
        or (until := subscription.ends_at(trainer)) is None
        or until.isoformat() != row.payload["until"]
    ):
        return None
    paid = trainer.pro_until is not None and trainer.pro_until >= until
    what = "Подписка Pro" if paid else "Пробный период Trenio"
    clients = await subscription.count_clients(session, trainer)
    terms = await subscription.get_terms(session)
    limit = terms.free_client_limit
    price = rubles(terms.price_month)
    if row.payload["days"] and until <= now:
        # Предупреждение опоздало: об окончании скажет следующее
        return None
    if row.payload["days"] == 0:
        head = f"⏳ {what} " + ("закончилась" if paid else "закончился")
        body = (
            "Всё, что уже есть, работает как раньше. "
            f"Но на бесплатном тарифе новых клиентов сверх {limit} не добавить"
        )
        tail = f"Pro без ограничений — {price} в месяц"
    else:
        day = until.astimezone(ZoneInfo(trainer.timezone)).date()
        days = (day - now.astimezone(ZoneInfo(trainer.timezone)).date()).days
        head = f"⏳ {what} закончится {in_days(max(days, 1))}, {day_month(day)}"
        body = f"Потом на бесплатном тарифе можно вести до {limit} клиентов, сейчас у вас {clients}"
        tail = f"Продлить Pro — {price} в месяц" if paid else f"Pro — {price} в месяц"
    return OutMessage(_lines(head, body, tail), open_subscription())


async def _client_limit(session: AsyncSession, row: Notification) -> OutMessage | None:
    client = await session.get(User, row.payload["user_id"])
    if client is None:
        return None
    limit = (await subscription.get_terms(session)).free_client_limit
    return OutMessage(
        _lines(
            f"🔒 {person(client)} хотел(а) стать вашим клиентом, но не смог(ла)",
            f"На бесплатном тарифе можно вести до {limit} клиентов. С Pro ограничений нет",
            "Когда оформите Pro, отправьте клиенту ссылку ещё раз",
        ),
        open_subscription(),
    )


def full_date(day: date) -> str:
    """«17 окт 2026»."""
    return f"{day_month(day)} {day.year}"


async def _subscription_paid(session: AsyncSession, row: Notification) -> OutMessage | None:
    payment = await session.get(SubscriptionPayment, row.payload["payment_id"])
    if payment is None or payment.status != "paid":
        return None
    trainer = await session.get(Trainer, payment.trainer_id)
    if trainer is None or trainer.pro_until is None:
        return None
    until = trainer.pro_until.astimezone(ZoneInfo(trainer.timezone)).date()
    paid = rubles(payment.amount) if payment.amount else None
    used = f"с баланса {rubles(payment.balance_used)}" if payment.balance_used else None
    how = ", ".join(part for part in (paid, used) if part)
    return OutMessage(
        _lines(
            f"✅ Pro оплачен, теперь он действует до {full_date(until)}",
            f"Оплачено: {how}",
            "Клиентов можно добавлять без ограничений. Спасибо, что вы с Trenio!",
        ),
        open_subscription("Открыть подписку"),
    )


async def _referral_bonus(session: AsyncSession, row: Notification) -> OutMessage | None:
    payment = await session.get(SubscriptionPayment, row.payload["payment_id"])
    inviter = await session.scalar(select(Trainer).where(Trainer.user_id == row.user_id))
    if payment is None or inviter is None:
        return None
    payer = await session.get(Trainer, payment.trainer_id)
    name = person(payer.user) if payer is not None else "Приглашённый тренер"
    return OutMessage(
        _lines(
            f"💰 {name} оплатил(а) Pro, вам начислено {rubles(row.payload['bonus'])}",
            f"Баланс: {rubles(inviter.balance)}. Он спишется, когда будете оплачивать подписку",
        ),
        open_app("Кто пришёл по ссылке", role=Role.TRAINER.value, tab="referrals"),
    )


def broadcast_message(text: str, with_button: bool) -> OutMessage:
    """Рассылка из админки; так же выглядит и тестовая отправка себе."""
    return OutMessage(text, open_app() if with_button else [])


async def _broadcast(session: AsyncSession, row: Notification) -> OutMessage | None:
    item = await session.get(Broadcast, row.payload["broadcast_id"])
    if item is None:
        return None
    return broadcast_message(item.text, item.with_button)


async def render(session: AsyncSession, row: Notification, now: datetime) -> OutMessage | None:
    kind = Kind(row.kind)
    if kind is Kind.BROADCAST:
        return await _broadcast(session, row)
    if kind is Kind.SUBSCRIPTION_PAID:
        return await _subscription_paid(session, row)
    if kind is Kind.REFERRAL_BONUS:
        return await _referral_bonus(session, row)
    if kind is Kind.TRAINER_JOINED:
        return await _trainer_joined(session, row)
    if kind is Kind.SUBSCRIPTION_ENDING:
        return await _subscription_ending(session, row, now)
    if kind is Kind.CLIENT_LIMIT:
        return await _client_limit(session, row)
    if kind is Kind.PACKAGE_LEFT:
        return await _package_left(session, row)
    if kind is Kind.PACKAGE_EXPIRING:
        return await _package_expiring(session, row, now)
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
            link = open_booking(booking, Role.TRAINER)
            if pending and booking.starts_at > now:
                return OutMessage(text, _confirm_buttons(booking) + link)
        case Kind.TRAINER_BOOKED:
            if not active:
                return None
            text = _lines(
                f"📅 Тренер {trainer} записал вас на тренировку",
                _session_line(booking),
                address(booking),
            )
            return OutMessage(
                text, client_cancel(booking, now) + open_booking(booking, Role.CLIENT)
            )
        case Kind.BOOKING_CONFIRMED:
            if not active:
                return None
            text = _lines(
                f"✅ Тренер {trainer} подтвердил запись",
                _session_line(booking),
                address(booking),
            )
            link = open_booking(booking, Role.CLIENT)
        case Kind.BOOKING_RESCHEDULED:
            return _rescheduled(booking, row, now)
        case Kind.BOOKING_DECLINED:
            text = _lines(
                f"Тренер {trainer} не сможет провести занятие в это время",
                _session_line(booking),
                _comment(booking.cancel_comment),
                "Выберите другое окошко в приложении.",
            )
            link = open_tab("Выбрать другое время", "book")
        case Kind.CLIENT_CANCELLED:
            text = _lines(
                f"❌ {client} отменил(а) запись",
                _session_line(booking),
                _comment(booking.cancel_comment),
            )
            link = open_client(booking.client_id)
        case Kind.TRAINER_CANCELLED:
            text = _lines(
                f"❌ Тренер {trainer} отменил запись",
                _session_line(booking),
                _comment(booking.cancel_comment),
            )
            link = open_tab("Записаться снова", "book")
    return OutMessage(text, link)
