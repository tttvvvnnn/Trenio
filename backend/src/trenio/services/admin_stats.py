"""Статистика платформы для админ-панели.

Деньги здесь только общие, по всей платформе: оборот отдельного тренера админ не видит.
По тренерам — только количества: клиенты, записи, когда заходил.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.db.models import (
    ACTIVE_BOOKING_STATUSES,
    Booking,
    Notification,
    Package,
    PackageSession,
    Payment,
    ScheduleDay,
    ScheduleRule,
    Service,
    Trainer,
    TrainerClient,
    TrainerInvite,
    User,
    UserActivityDay,
)
from trenio.services.packages import CHARGED

# Недели и месяцы в админке считаем по Москве
ADMIN_TIMEZONE = ZoneInfo("Europe/Moscow")
WEEKS = 8
# Тренер без записей дольше этого — «затих»
QUIET_DAYS = 14
# Окно активности тренера: полоска дней в админке
ACTIVITY_DAYS = 14
# Тренер «пользуется» Trenio, если заходил хотя бы столько дней из окна: критерий беты
ENGAGED_DAYS = 10


async def mark_active(session: AsyncSession, user_id: int, now: datetime) -> None:
    """Отмечает, что человек открывал приложение сегодня. Коммит — за вызывающим."""
    day = now.astimezone(ADMIN_TIMEZONE).date()
    await session.execute(
        insert(UserActivityDay).values(user_id=user_id, day=day).on_conflict_do_nothing()
    )


def activity_window(now: datetime) -> list[date]:
    """Дни окна активности, от самого старого до сегодняшнего."""
    today = now.astimezone(ADMIN_TIMEZONE).date()
    return [today - timedelta(days=offset) for offset in range(ACTIVITY_DAYS - 1, -1, -1)]


async def _active_days(session: AsyncSession, since: date) -> dict[int, set[date]]:
    rows = await session.execute(
        select(UserActivityDay.user_id, UserActivityDay.day).where(UserActivityDay.day >= since)
    )
    result: dict[int, set[date]] = {}
    for user_id, day in rows.all():
        result.setdefault(int(user_id), set()).add(day)
    return result


def streak(days: set[date], today: date) -> int:
    """Сколько дней подряд человек заходил. Сегодня ещё не заходил — считаем со вчера."""
    day = today if today in days else today - timedelta(days=1)
    count = 0
    while day in days:
        count += 1
        day -= timedelta(days=1)
    return count


async def _count(session: AsyncSession, *conditions: ColumnElement[bool], of: object) -> int:
    stmt = select(func.count(func.distinct(of))).where(*conditions)
    return int(await session.scalar(stmt) or 0)


def _held(since: datetime, until: datetime) -> ColumnElement[bool]:
    """Записи, которые были или будут в промежутке: активные или отмеченные."""
    return and_(
        Booking.starts_at >= since,
        Booking.starts_at < until,
        or_(Booking.status.in_(ACTIVE_BOOKING_STATUSES), Booking.attendance.is_not(None)),
    )


def local_midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=ADMIN_TIMEZONE)


@dataclass(frozen=True)
class Week:
    # Понедельник недели
    start: date
    new_clients: int
    new_trainers: int


@dataclass(frozen=True)
class Funnel:
    trainers: int
    onboarded: int
    set_up: int
    with_clients: int
    with_bookings: int


@dataclass(frozen=True)
class Money:
    month: str
    received: int
    received_prev: int
    packages_sold: int
    packages_amount: int


@dataclass(frozen=True)
class Overview:
    users: int
    users_seen_week: int
    users_active_today: int
    # Действующие тренеры, которые заходили ENGAGED_DAYS из ACTIVITY_DAYS дней
    trainers_engaged: int
    trainers: int
    trainers_active: int
    trainers_disabled: int
    clients: int
    clients_new_week: int
    # Клиенты без Telegram, которых завели тренеры; в users не входят
    clients_offline: int
    bookings_week: int
    attended_week: int
    upcoming_week: int
    invites_open: int
    notifications_sent_day: int
    notifications_failed_day: int
    weeks: list[Week]
    funnel: Funnel
    money: Money


async def set_up_trainers(session: AsyncSession) -> set[int]:
    """Тренеры, у которых есть и активная услуга, и рабочие часы."""
    with_service = set(
        (await session.scalars(select(Service.trainer_id).where(Service.is_active))).all()
    )
    with_hours = set((await session.scalars(select(ScheduleRule.trainer_id))).all()) | set(
        (
            await session.scalars(
                select(ScheduleDay.trainer_id).where(
                    func.jsonb_array_length(ScheduleDay.windows) > 0
                )
            )
        ).all()
    )
    return with_service & with_hours


async def _received(session: AsyncSession, first: date, last: date) -> int:
    """Все деньги платформы за дни first…last: оплаты блоков и разовые занятия."""
    payments = await session.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.paid_on >= first, Payment.paid_on <= last
        )
    )
    one_offs = await session.scalar(
        select(func.coalesce(func.sum(Booking.price), 0))
        .select_from(Booking)
        .outerjoin(PackageSession, PackageSession.booking_id == Booking.id)
        .where(
            Booking.attendance.in_(CHARGED),
            PackageSession.id.is_(None),
            Booking.starts_at >= local_midnight(first),
            Booking.starts_at < local_midnight(last + timedelta(days=1)),
        )
    )
    return int(payments or 0) + int(one_offs or 0)


def _month_bounds(day: date) -> tuple[date, date]:
    first = day.replace(day=1)
    following = (first + timedelta(days=32)).replace(day=1)
    return first, following - timedelta(days=1)


async def overview(session: AsyncSession, now: datetime) -> Overview:
    week_ago = now - timedelta(days=7)
    day_ago = now - timedelta(days=1)
    trainers = (await session.scalars(select(Trainer))).all()
    active = [t for t in trainers if t.is_active]
    active_ids = {t.id for t in active}

    today = now.astimezone(ADMIN_TIMEZONE).date()
    activity = await _active_days(session, activity_window(now)[0])
    monday = today - timedelta(days=today.weekday())
    weeks = []
    for offset in range(WEEKS - 1, -1, -1):
        start = monday - timedelta(weeks=offset)
        since, until = local_midnight(start), local_midnight(start + timedelta(days=7))
        weeks.append(
            Week(
                start=start,
                new_clients=await _count(
                    session,
                    TrainerClient.created_at >= since,
                    TrainerClient.created_at < until,
                    of=TrainerClient.user_id,
                ),
                new_trainers=sum(1 for t in trainers if since <= t.created_at < until),
            )
        )

    with_clients = set((await session.scalars(select(TrainerClient.trainer_id).distinct())).all())
    with_bookings = set(
        (
            await session.scalars(select(Booking.trainer_id).where(_held(week_ago, now)).distinct())
        ).all()
    )
    set_up = await set_up_trainers(session)
    funnel = Funnel(
        trainers=len(active),
        onboarded=sum(1 for t in active if t.onboarded_at is not None),
        set_up=len(active_ids & set_up),
        with_clients=len(active_ids & with_clients),
        with_bookings=len(active_ids & with_bookings),
    )

    first, last = _month_bounds(today)
    prev_first, prev_last = _month_bounds(first - timedelta(days=1))
    sold = (
        await session.execute(
            select(func.count(Package.id), func.coalesce(func.sum(Package.price), 0)).where(
                Package.purchased_on >= first, Package.purchased_on <= last
            )
        )
    ).one()
    money = Money(
        month=f"{first.year:04d}-{first.month:02d}",
        received=await _received(session, first, last),
        received_prev=await _received(session, prev_first, prev_last),
        packages_sold=int(sold[0]),
        packages_amount=int(sold[1]),
    )

    return Overview(
        users=await _count(session, User.telegram_id.is_not(None), of=User.id),
        users_seen_week=await _count(session, User.last_seen_at >= week_ago, of=User.id),
        users_active_today=await _count(
            session, UserActivityDay.day == today, of=UserActivityDay.user_id
        ),
        trainers_engaged=sum(
            1 for t in active if len(activity.get(t.user_id, set())) >= ENGAGED_DAYS
        ),
        trainers=len(trainers),
        trainers_active=len(active),
        trainers_disabled=len(trainers) - len(active),
        clients=await _count(session, of=TrainerClient.user_id),
        clients_new_week=await _count(
            session, TrainerClient.created_at >= week_ago, of=TrainerClient.user_id
        ),
        clients_offline=await _count(session, User.telegram_id.is_(None), of=User.id),
        bookings_week=await _count(session, _held(week_ago, now), of=Booking.id),
        attended_week=await _count(
            session, _held(week_ago, now), Booking.attendance == "attended", of=Booking.id
        ),
        upcoming_week=await _count(session, _held(now, now + timedelta(days=7)), of=Booking.id),
        invites_open=await _count(
            session,
            TrainerInvite.used_by_id.is_(None),
            TrainerInvite.expires_at > now,
            of=TrainerInvite.id,
        ),
        notifications_sent_day=await _count(
            session,
            Notification.sent_at >= day_ago,
            Notification.status == "sent",
            of=Notification.id,
        ),
        notifications_failed_day=await _count(
            session,
            Notification.send_at >= day_ago,
            Notification.status == "failed",
            of=Notification.id,
        ),
        weeks=weeks,
        funnel=funnel,
        money=money,
    )


# --- Тренеры ---


class TrainerState(StrEnum):
    ACTIVE = "active"
    # Нет записей последние две недели
    QUIET = "quiet"
    # Не прошёл настройку или нет услуги и часов
    NOT_SET_UP = "not_set_up"
    DISABLED = "disabled"


@dataclass(frozen=True)
class TrainerRow:
    trainer: Trainer
    state: TrainerState
    clients: int
    clients_new_week: int
    bookings_month: int
    attended_month: int
    services: int
    last_booking_at: datetime | None
    # Заходил ли в каждый день окна, от старого к сегодняшнему
    active_days: list[bool]
    streak: int
    # За окно активности: сколько записей поставил сам и сколько занятий отметил
    bookings_created: int
    marks: int


async def per_trainer(
    session: AsyncSession, column: object, *conditions: ColumnElement[bool], of: object
) -> dict[int, int]:
    stmt = (
        select(column, func.count(func.distinct(of)))  # type: ignore[call-overload]
        .where(*conditions)
        .group_by(column)
    )
    return {int(key): int(value) for key, value in (await session.execute(stmt)).all()}


async def trainer_rows(session: AsyncSession, now: datetime) -> list[TrainerRow]:
    trainers: Sequence[Trainer] = (await session.scalars(select(Trainer))).all()
    month_ago = now - timedelta(days=30)
    clients = await per_trainer(session, TrainerClient.trainer_id, of=TrainerClient.user_id)
    clients_new = await per_trainer(
        session,
        TrainerClient.trainer_id,
        TrainerClient.created_at >= now - timedelta(days=7),
        of=TrainerClient.user_id,
    )
    bookings = await per_trainer(session, Booking.trainer_id, _held(month_ago, now), of=Booking.id)
    attended = await per_trainer(
        session,
        Booking.trainer_id,
        _held(month_ago, now),
        Booking.attendance == "attended",
        of=Booking.id,
    )
    services = await per_trainer(
        session, Service.trainer_id, Service.is_active.is_(True), of=Service.id
    )
    last_booking = {
        int(trainer_id): starts_at
        for trainer_id, starts_at in (
            await session.execute(
                select(Booking.trainer_id, func.max(Booking.starts_at))
                .where(
                    Booking.starts_at <= now,
                    or_(
                        Booking.status.in_(ACTIVE_BOOKING_STATUSES),
                        Booking.attendance.is_not(None),
                    ),
                )
                .group_by(Booking.trainer_id)
            )
        ).all()
    }
    window = activity_window(now)
    window_start = local_midnight(window[0])
    activity = await _active_days(session, window[0])
    created = await per_trainer(
        session,
        Booking.trainer_id,
        Booking.created_by == "trainer",
        Booking.created_at >= window_start,
        of=Booking.id,
    )
    marks = await per_trainer(
        session, Booking.trainer_id, Booking.attendance_marked_at >= window_start, of=Booking.id
    )
    set_up = await set_up_trainers(session)
    rows = []
    for trainer in trainers:
        days = activity.get(trainer.user_id, set())
        last = last_booking.get(trainer.id)
        if not trainer.is_active:
            state = TrainerState.DISABLED
        elif trainer.onboarded_at is None or trainer.id not in set_up:
            state = TrainerState.NOT_SET_UP
        elif last is None or last < now - timedelta(days=QUIET_DAYS):
            state = TrainerState.QUIET
        else:
            state = TrainerState.ACTIVE
        rows.append(
            TrainerRow(
                trainer=trainer,
                state=state,
                clients=clients.get(trainer.id, 0),
                clients_new_week=clients_new.get(trainer.id, 0),
                bookings_month=bookings.get(trainer.id, 0),
                attended_month=attended.get(trainer.id, 0),
                services=services.get(trainer.id, 0),
                last_booking_at=last,
                active_days=[day in days for day in window],
                streak=streak(days, window[-1]),
                bookings_created=created.get(trainer.id, 0),
                marks=marks.get(trainer.id, 0),
            )
        )
    order = list(TrainerState)
    rows.sort(key=lambda r: (order.index(r.state), -r.bookings_month, r.trainer.id))
    return rows


async def open_invites(session: AsyncSession, now: datetime) -> Sequence[TrainerInvite]:
    stmt = (
        select(TrainerInvite)
        .where(TrainerInvite.used_by_id.is_(None), TrainerInvite.expires_at > now)
        .order_by(TrainerInvite.expires_at)
    )
    return (await session.scalars(stmt)).all()
