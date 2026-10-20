"""Клиенты платформы в админке: поиск, история и удаление данных по запросу.

Как и с тренерами, админ видит только количества и даты: ни денег клиента у тренера,
ни заметок, ни телефона. Клиент здесь — человек, у которого есть хотя бы один тренер.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import ColumnElement, Select, String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.db.models import (
    Booking,
    Package,
    Service,
    Trainer,
    TrainerClient,
    User,
    UserActivityDay,
)
from trenio.services.admin_stats import ADMIN_TIMEZONE

SEARCH_LIMIT = 100
HISTORY_LIMIT = 30
# Полоска активности в карточке клиента
ACTIVITY_DAYS = 30


@dataclass(frozen=True, slots=True)
class TrainerRef:
    id: int
    name: str


@dataclass(frozen=True, slots=True)
class ClientRow:
    user: User
    trainers: list[TrainerRef]
    since: datetime
    bookings: int
    attended: int
    last_booking_at: datetime | None
    next_booking_at: datetime | None
    # Дней с заходом в приложение за последние две недели
    active_days: int


@dataclass(frozen=True, slots=True)
class ClientLink:
    trainer: TrainerRef
    since: datetime
    bookings: int
    attended: int
    missed: int
    cancelled: int
    # Блоки, из которых ещё можно списывать
    open_packages: int
    last_booking_at: datetime | None
    next_booking_at: datetime | None


@dataclass(frozen=True, slots=True)
class HistoryRow:
    starts_at: datetime
    trainer: str
    service: str
    status: str
    attendance: str | None
    created_by: str


@dataclass(frozen=True, slots=True)
class ClientCard:
    row: ClientRow
    is_trainer: bool
    links: list[ClientLink]
    history: list[HistoryRow]
    # Заходил ли в каждый из последних ACTIVITY_DAYS дней, от старого к сегодняшнему
    activity: list[bool]


def _search(query: str) -> Select[int]:
    """id клиентов, у которых совпало имя, @username, Telegram ID или имя тренера."""
    text = query.strip().lstrip("@")
    base = select(TrainerClient.user_id).join(User, User.id == TrainerClient.user_id)
    if not text:
        return base
    like = f"%{text}%"
    full_name = func.concat_ws(" ", User.first_name, User.last_name)
    conditions: list[ColumnElement[bool]] = [
        full_name.ilike(like),
        User.username.ilike(like),
        TrainerClient.trainer_id.in_(select(Trainer.id).where(Trainer.display_name.ilike(like))),
    ]
    if text.isdigit() and len(text) <= 18:
        conditions.append(cast(User.telegram_id, String).like(like))
        conditions.append(User.id == int(text))
    return base.where(or_(*conditions))


async def _rows(session: AsyncSession, user_ids: list[int], now: datetime) -> list[ClientRow]:
    if not user_ids:
        return []
    users = {
        u.id: u for u in (await session.scalars(select(User).where(User.id.in_(user_ids)))).all()
    }
    trainers: dict[int, list[TrainerRef]] = defaultdict(list)
    since: dict[int, datetime] = {}
    links = await session.execute(
        select(TrainerClient.user_id, Trainer.id, Trainer.display_name, TrainerClient.created_at)
        .join(Trainer, Trainer.id == TrainerClient.trainer_id)
        .where(TrainerClient.user_id.in_(user_ids))
        .order_by(TrainerClient.created_at)
    )
    for user_id, trainer_id, name, created_at in links.all():
        trainers[user_id].append(TrainerRef(trainer_id, name))
        since.setdefault(user_id, created_at)

    held = Booking.status == "confirmed"
    stats = await session.execute(
        select(
            Booking.client_id,
            func.count().filter(Booking.status.in_(("pending", "confirmed"))),
            func.count().filter(Booking.attendance == "attended"),
            func.max(Booking.starts_at).filter(held, Booking.starts_at <= now),
            func.min(Booking.starts_at).filter(held, Booking.starts_at > now),
        )
        .where(Booking.client_id.in_(user_ids))
        .group_by(Booking.client_id)
    )
    by_user = {row[0]: row[1:] for row in stats.all()}

    today = now.astimezone(ADMIN_TIMEZONE).date()
    days = dict(
        (
            await session.execute(
                select(UserActivityDay.user_id, func.count())
                .where(
                    UserActivityDay.user_id.in_(user_ids),
                    UserActivityDay.day > today - timedelta(days=14),
                )
                .group_by(UserActivityDay.user_id)
            )
        ).all()
    )

    rows = []
    for user_id in user_ids:
        user = users.get(user_id)
        if user is None:
            continue
        total, attended, last, upcoming = by_user.get(user_id, (0, 0, None, None))
        rows.append(
            ClientRow(
                user=user,
                trainers=trainers[user_id],
                since=since.get(user_id, user.created_at),
                bookings=total,
                attended=attended,
                last_booking_at=last,
                next_booking_at=upcoming,
                active_days=days.get(user_id, 0),
            )
        )
    return rows


async def search(
    session: AsyncSession, query: str, now: datetime, *, deleted: bool = False
) -> list[ClientRow]:
    """Свежие клиенты сверху. Удалённые аккаунты только по флагу: их почти не ищут."""
    matched = _search(query).subquery()
    newest = func.max(TrainerClient.created_at)
    found = (
        select(TrainerClient.user_id)
        .join(User, User.id == TrainerClient.user_id)
        .where(TrainerClient.user_id.in_(select(matched.c.user_id)))
        .where(User.deleted_at.is_not(None) if deleted else User.deleted_at.is_(None))
        .group_by(TrainerClient.user_id)
        .order_by(newest.desc())
        .limit(SEARCH_LIMIT)
    )
    return await _rows(session, list((await session.scalars(found)).all()), now)


async def card(session: AsyncSession, user_id: int, now: datetime) -> ClientCard | None:
    rows = await _rows(session, [user_id], now)
    if not rows or not rows[0].trainers:
        return None
    row = rows[0]

    held = Booking.status == "confirmed"
    per_trainer = await session.execute(
        select(
            Booking.trainer_id,
            func.count().filter(Booking.status.in_(("pending", "confirmed"))),
            func.count().filter(Booking.attendance == "attended"),
            func.count().filter(Booking.attendance.in_(("missed_charged", "missed_free"))),
            func.count().filter(Booking.status.in_(("cancelled", "declined"))),
            func.max(Booking.starts_at).filter(held, Booking.starts_at <= now),
            func.min(Booking.starts_at).filter(held, Booking.starts_at > now),
        )
        .where(Booking.client_id == user_id)
        .group_by(Booking.trainer_id)
    )
    bookings = {r[0]: r[1:] for r in per_trainer.all()}
    today = now.astimezone(ADMIN_TIMEZONE).date()
    open_packages = dict(
        (
            await session.execute(
                select(Package.trainer_id, func.count())
                .where(
                    Package.client_id == user_id,
                    Package.closed_at.is_(None),
                    or_(Package.valid_until.is_(None), Package.valid_until >= today),
                )
                .group_by(Package.trainer_id)
            )
        ).all()
    )
    joined = dict(
        (
            await session.execute(
                select(TrainerClient.trainer_id, TrainerClient.created_at).where(
                    TrainerClient.user_id == user_id
                )
            )
        ).all()
    )
    links = []
    for trainer in row.trainers:
        total, attended, missed, cancelled, last, upcoming = bookings.get(
            trainer.id, (0, 0, 0, 0, None, None)
        )
        links.append(
            ClientLink(
                trainer=trainer,
                since=joined[trainer.id],
                bookings=total,
                attended=attended,
                missed=missed,
                cancelled=cancelled,
                open_packages=open_packages.get(trainer.id, 0),
                last_booking_at=last,
                next_booking_at=upcoming,
            )
        )

    history = [
        HistoryRow(
            starts_at=starts_at,
            trainer=trainer_name,
            service=service_name,
            status=status,
            attendance=attendance,
            created_by=created_by,
        )
        for starts_at, trainer_name, service_name, status, attendance, created_by in (
            await session.execute(
                select(
                    Booking.starts_at,
                    Trainer.display_name,
                    Service.name,
                    Booking.status,
                    Booking.attendance,
                    Booking.created_by,
                )
                .join(Trainer, Trainer.id == Booking.trainer_id)
                .join(Service, Service.id == Booking.service_id)
                .where(Booking.client_id == user_id)
                .order_by(Booking.starts_at.desc())
                .limit(HISTORY_LIMIT)
            )
        ).all()
    ]

    window = [today - timedelta(days=offset) for offset in range(ACTIVITY_DAYS - 1, -1, -1)]
    seen: set[date] = set(
        (
            await session.scalars(
                select(UserActivityDay.day).where(
                    UserActivityDay.user_id == user_id, UserActivityDay.day >= window[0]
                )
            )
        ).all()
    )
    is_trainer = await session.scalar(select(Trainer.id).where(Trainer.user_id == user_id))
    return ClientCard(
        row=row,
        is_trainer=is_trainer is not None,
        links=links,
        history=history,
        activity=[day in seen for day in window],
    )
