"""Статистика тренера за месяц: посещаемость, загрузка по дням недели, клиенты.

Деньги здесь не считаем, они в финансах. Месяц — по часовому поясу тренера.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.db.models import ACTIVE_BOOKING_STATUSES, Booking, Trainer, TrainerClient, User
from trenio.services.finance import month_start, shift_month
from trenio.services.schedule import day_hours

# Клиент «пропал», если не был на занятиях столько дней и не записан на будущее
LAPSED_DAYS = 21
TOP_CLIENTS = 5


@dataclass(frozen=True)
class Visits:
    attended: int
    missed_charged: int
    missed_free: int
    # Прошли, но тренер ещё не отметил
    unmarked: int
    # Ещё впереди в этом месяце
    upcoming: int
    cancelled_by_client: int
    cancelled_by_trainer: int


@dataclass(frozen=True)
class WeekdayLoad:
    # 0 — понедельник
    weekday: int
    # Часы в расписании и сколько из них занято записями
    open_minutes: int
    booked_minutes: int


@dataclass(frozen=True)
class ClientVisits:
    user: User
    sessions: int


@dataclass(frozen=True)
class LapsedClient:
    user: User
    last_at: datetime


@dataclass(frozen=True)
class Stats:
    month: str
    visits: Visits
    load: list[WeekdayLoad]
    new_clients: int
    top: list[ClientVisits]
    lapsed: list[LapsedClient]


def _midnight(day: date, zone: ZoneInfo) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=zone)


async def month_stats(session: AsyncSession, trainer: Trainer, month: str, now: datetime) -> Stats:
    zone = ZoneInfo(trainer.timezone)
    first = month_start(month)
    after = month_start(shift_month(month, 1))
    since, until = _midnight(first, zone), _midnight(after, zone)

    bookings = (
        await session.scalars(
            select(Booking).where(
                Booking.trainer_id == trainer.id,
                Booking.starts_at >= since,
                Booking.starts_at < until,
            )
        )
    ).all()
    visits = _visits(bookings, now)

    # Загрузка: занятое записями время к часам расписания, по дням недели.
    # Групповое занятие занимает время один раз, сколько бы человек ни пришло
    hours = await day_hours(session, trainer, first, (after - first).days)
    open_minutes = [0] * 7
    for item in hours:
        for window in item.windows:
            start = datetime.combine(item.day, window.start)
            end = datetime.combine(item.day, window.end)
            open_minutes[item.day.weekday()] += int((end - start).total_seconds() // 60)
    booked_minutes = [0] * 7
    busy = {
        (b.starts_at, b.ends_at)
        for b in bookings
        if b.status in ACTIVE_BOOKING_STATUSES or b.attendance is not None
    }
    for starts_at, ends_at in busy:
        weekday = starts_at.astimezone(zone).weekday()
        booked_minutes[weekday] += int((ends_at - starts_at).total_seconds() // 60)
    load = [WeekdayLoad(day, open_minutes[day], booked_minutes[day]) for day in range(7)]

    new_clients = int(
        await session.scalar(
            select(func.count(TrainerClient.id)).where(
                TrainerClient.trainer_id == trainer.id,
                TrainerClient.created_at >= since,
                TrainerClient.created_at < until,
            )
        )
        or 0
    )

    attended = Counter(b.client_id for b in bookings if b.attendance == "attended")
    users = await _users(session, set(attended))
    top = [
        ClientVisits(users[client_id], count)
        for client_id, count in attended.most_common(TOP_CLIENTS)
        if client_id in users
    ]
    return Stats(
        month=month,
        visits=visits,
        load=load,
        new_clients=new_clients,
        top=top,
        lapsed=await lapsed_clients(session, trainer, now),
    )


def _visits(bookings: Sequence[Booking], now: datetime) -> Visits:
    active = [b for b in bookings if b.status in ACTIVE_BOOKING_STATUSES]
    return Visits(
        attended=sum(1 for b in bookings if b.attendance == "attended"),
        missed_charged=sum(1 for b in bookings if b.attendance == "missed_charged"),
        missed_free=sum(1 for b in bookings if b.attendance == "missed_free"),
        unmarked=sum(1 for b in active if b.attendance is None and b.starts_at <= now),
        upcoming=sum(1 for b in active if b.starts_at > now),
        cancelled_by_client=sum(
            1 for b in bookings if b.status == "cancelled" and b.cancelled_by == "client"
        ),
        cancelled_by_trainer=sum(
            1 for b in bookings if b.status == "cancelled" and b.cancelled_by == "trainer"
        ),
    )


async def _users(session: AsyncSession, ids: set[int]) -> dict[int, User]:
    if not ids:
        return {}
    found = (await session.scalars(select(User).where(User.id.in_(ids)))).all()
    return {user.id: user for user in found}


async def lapsed_clients(
    session: AsyncSession, trainer: Trainer, now: datetime
) -> list[LapsedClient]:
    """Клиенты, которые раньше ходили, но давно не были и не записаны на будущее."""
    held = or_(Booking.status.in_(ACTIVE_BOOKING_STATUSES), Booking.attendance.is_not(None))
    last = (
        await session.execute(
            select(Booking.client_id, func.max(Booking.starts_at))
            .where(Booking.trainer_id == trainer.id, Booking.starts_at <= now, held)
            .group_by(Booking.client_id)
        )
    ).all()
    future = set(
        (
            await session.scalars(
                select(Booking.client_id).where(
                    Booking.trainer_id == trainer.id,
                    Booking.starts_at > now,
                    Booking.status.in_(ACTIVE_BOOKING_STATUSES),
                )
            )
        ).all()
    )
    linked = set(
        (
            await session.scalars(
                select(TrainerClient.user_id).where(TrainerClient.trainer_id == trainer.id)
            )
        ).all()
    )
    border = now - timedelta(days=LAPSED_DAYS)
    candidates = {
        int(client_id): last_at
        for client_id, last_at in last
        if last_at < border and client_id not in future and client_id in linked
    }
    users = await _users(session, set(candidates))
    result = [
        LapsedClient(users[client_id], last_at)
        for client_id, last_at in candidates.items()
        if client_id in users and not users[client_id].is_deleted
    ]
    # Недавно пропавшие первыми: их проще вернуть
    result.sort(key=lambda item: item.last_at, reverse=True)
    return result
