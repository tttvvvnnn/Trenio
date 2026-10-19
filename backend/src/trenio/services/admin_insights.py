"""Главный экран админки: растёт ли Trenio, кому из тренеров нужна помощь, что происходит.

Как и вся админка, без денег отдельных тренеров: только события и количества.
"""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from sqlalchemy import ColumnElement, and_, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.db.models import (
    ACTIVE_BOOKING_STATUSES,
    Booking,
    ClientError,
    ClientMeasurement,
    Notification,
    Package,
    Trainer,
    TrainerClient,
    TrainerInvite,
    User,
)
from trenio.services.admin_stats import (
    ADMIN_TIMEZONE,
    local_midnight,
    per_trainer,
    set_up_trainers,
)
from trenio.services.packages import CHARGED

# Тренер «живой», если за последние 7 дней у него прошло хотя бы одно занятие
WINDOW = timedelta(days=7)
# Сколько окон по 7 дней показываем на графике
SERIES = 8
# Когда тренер «требует внимания»
STUCK_SETUP = timedelta(days=2)
NO_CLIENTS = timedelta(days=3)
QUIET_AFTER = timedelta(days=7)
UNMARKED_LIMIT = 5
# Лента событий
FEED_DAYS = 30
FEED_LIMIT = 30
# Удержание: недели прихода и через сколько недель проверяем
COHORT_WEEKS = 6
COHORT_POINTS = (1, 2, 4)
# Чем пользуются: за последние 30 дней
USAGE_WINDOW = timedelta(days=30)


def done(since: datetime | None, until: datetime) -> ColumnElement[bool]:
    """Занятия в промежутке, которые состоялись: не отменены и не пропущены без списания.

    Неотмеченное подтверждённое занятие считаем прошедшим: многие тренеры не отмечают.
    since=None — с самого начала.
    """
    return and_(
        Booking.starts_at >= since if since is not None else true(),
        Booking.starts_at < until,
        or_(
            and_(Booking.status.in_(ACTIVE_BOOKING_STATUSES), Booking.attendance.is_(None)),
            Booking.attendance.in_(CHARGED),
        ),
    )


# --- Растёт ли Trenio ---


@dataclass(frozen=True)
class Pulse:
    # По окнам в 7 дней, от старого к последнему (оно кончается сейчас)
    live_trainers: list[int]
    sessions: list[int]
    # Доля записей, которые клиенты сделали сами, в процентах; None — записей не было
    self_booked: list[int | None]


def _window(at: datetime, now: datetime) -> int | None:
    """Номер окна от последнего: 0 — последние 7 дней. None — вне графика."""
    if at >= now:
        return None
    index = int((now - at) / WINDOW)
    return index if index < SERIES else None


async def pulse(session: AsyncSession, now: datetime) -> Pulse:
    since = now - WINDOW * SERIES
    live: list[set[int]] = [set() for _ in range(SERIES)]
    sessions = [0] * SERIES
    rows = await session.execute(
        select(Booking.trainer_id, Booking.starts_at).where(done(since, now))
    )
    for trainer_id, starts_at in rows.all():
        index = _window(starts_at, now)
        if index is not None:
            live[index].add(int(trainer_id))
            sessions[index] += 1

    created = [0] * SERIES
    by_client = [0] * SERIES
    made = await session.execute(
        select(Booking.created_at, Booking.created_by).where(Booking.created_at >= since)
    )
    for created_at, created_by in made.all():
        index = _window(created_at, now)
        if index is not None:
            created[index] += 1
            by_client[index] += created_by == "client"

    oldest_first = range(SERIES - 1, -1, -1)
    return Pulse(
        live_trainers=[len(live[i]) for i in oldest_first],
        sessions=[sessions[i] for i in oldest_first],
        self_booked=[
            round(by_client[i] * 100 / created[i]) if created[i] else None for i in oldest_first
        ],
    )


# --- Первые шаги тренера: для ленты и карточки ---


@dataclass(frozen=True)
class Firsts:
    client: dict[int, datetime]
    client_booking: dict[int, datetime]
    package: dict[int, datetime]


async def _first(
    session: AsyncSession, column: object, at: object, *conditions: object
) -> dict[int, datetime]:
    stmt = select(column, func.min(at)).where(*conditions).group_by(column)  # type: ignore[call-overload]
    return {int(key): value for key, value in (await session.execute(stmt)).all()}


async def firsts(session: AsyncSession) -> Firsts:
    return Firsts(
        client=await _first(session, TrainerClient.trainer_id, TrainerClient.created_at),
        client_booking=await _first(
            session, Booking.trainer_id, Booking.created_at, Booking.created_by == "client"
        ),
        package=await _first(session, Package.trainer_id, Package.created_at),
    )


async def _last_done(session: AsyncSession, now: datetime) -> dict[int, datetime]:
    stmt = (
        select(Booking.trainer_id, func.max(Booking.starts_at))
        .where(done(None, now))
        .group_by(Booking.trainer_id)
    )
    return {int(key): value for key, value in (await session.execute(stmt)).all()}


# --- Кому нужна помощь ---


class Reason(StrEnum):
    # Нет услуги или рабочих часов
    NOT_SET_UP = "not_set_up"
    NO_CLIENTS = "no_clients"
    # Были занятия, а теперь неделю нет
    QUIET = "quiet"
    # Прошедшие занятия без отметки: блоки и финансы у тренера врут
    UNMARKED = "unmarked"


@dataclass(frozen=True)
class Attention:
    trainer: Trainer
    reason: Reason
    # Сколько дней длится; для UNMARKED — сколько занятий без отметки
    count: int


async def attention(
    session: AsyncSession, now: datetime, admin_telegram_ids: Collection[int]
) -> list[Attention]:
    """Действующие тренеры, которым стоит написать. Админов не показываем."""
    trainers = [
        t
        for t in (await session.scalars(select(Trainer).where(Trainer.is_active))).all()
        if t.user.telegram_id not in admin_telegram_ids
    ]
    set_up = await set_up_trainers(session)
    clients = await per_trainer(session, TrainerClient.trainer_id, of=TrainerClient.user_id)
    last = await _last_done(session, now)
    unmarked = await per_trainer(
        session,
        Booking.trainer_id,
        Booking.status.in_(ACTIVE_BOOKING_STATUSES),
        Booking.attendance.is_(None),
        Booking.ends_at < now,
        of=Booking.id,
    )
    result = []
    for trainer in trainers:
        ready = trainer.onboarded_at is not None and trainer.id in set_up
        if not ready:
            if now - trainer.created_at >= STUCK_SETUP:
                result.append(
                    Attention(trainer, Reason.NOT_SET_UP, (now - trainer.created_at).days)
                )
            continue
        if clients.get(trainer.id, 0) == 0:
            since = trainer.onboarded_at or trainer.created_at
            if now - since >= NO_CLIENTS:
                result.append(Attention(trainer, Reason.NO_CLIENTS, (now - since).days))
            continue
        last_at = last.get(trainer.id)
        if last_at is not None and now - last_at >= QUIET_AFTER:
            result.append(Attention(trainer, Reason.QUIET, (now - last_at).days))
            continue
        if unmarked.get(trainer.id, 0) >= UNMARKED_LIMIT:
            result.append(Attention(trainer, Reason.UNMARKED, unmarked[trainer.id]))
    order = list(Reason)
    result.sort(key=lambda a: (order.index(a.reason), -a.count, a.trainer.id))
    return result


# --- Лента ---


class EventKind(StrEnum):
    JOINED = "joined"
    FIRST_CLIENT = "first_client"
    FIRST_CLIENT_BOOKING = "first_client_booking"
    FIRST_PACKAGE = "first_package"
    QUIET = "quiet"
    ERROR = "error"


@dataclass(frozen=True)
class Event:
    at: datetime
    kind: EventKind
    text: str
    trainer_id: int | None = None


def _name(user: User) -> str:
    return " ".join(part for part in (user.first_name, user.last_name) if part)


async def feed(session: AsyncSession, now: datetime, first: Firsts) -> list[Event]:
    since = now - timedelta(days=FEED_DAYS)
    trainers = {t.id: t for t in (await session.scalars(select(Trainer))).all()}
    inviters = {
        used_by: _name(user)
        for used_by, user in (
            await session.execute(
                select(TrainerInvite.used_by_id, User)
                .join(User, User.id == TrainerInvite.created_by_id)
                .where(TrainerInvite.used_by_id.is_not(None))
            )
        ).all()
    }
    events = []
    for trainer in trainers.values():
        if trainer.created_at >= since:
            inviter = inviters.get(trainer.user_id)
            text = f"{trainer.display_name}: новый тренер"
            if inviter:
                text += f", пригласил(а) {inviter}"
            events.append(Event(trainer.created_at, EventKind.JOINED, text, trainer.id))
    steps = (
        (first.client, EventKind.FIRST_CLIENT, "первый клиент"),
        (first.client_booking, EventKind.FIRST_CLIENT_BOOKING, "клиент впервые записался сам"),
        (first.package, EventKind.FIRST_PACKAGE, "продан первый блок"),
    )
    for dates, kind, what in steps:
        for trainer_id, at in dates.items():
            owner = trainers.get(trainer_id)
            if owner is not None and at >= since:
                events.append(Event(at, kind, f"{owner.display_name}: {what}", trainer_id))
    for trainer_id, last_at in (await _last_done(session, now)).items():
        owner = trainers.get(trainer_id)
        quiet_at = last_at + QUIET_AFTER
        if owner is not None and owner.is_active and since <= quiet_at <= now:
            text = f"{owner.display_name}: неделя без занятий"
            events.append(Event(quiet_at, EventKind.QUIET, text, trainer_id))

    # Одинаковые ошибки за день склеиваем в одно событие
    errors: dict[tuple[str, date], tuple[datetime, int, str | None]] = {}
    rows = await session.execute(
        select(ClientError.message, ClientError.screen, ClientError.created_at).where(
            ClientError.created_at >= since
        )
    )
    for message, screen, at in rows.all():
        key = (message, at.astimezone(ADMIN_TIMEZONE).date())
        latest, count, _ = errors.get(key, (at, 0, screen))
        errors[key] = (max(latest, at), count + 1, screen)
    for (message, _), (at, count, screen) in errors.items():
        text = f"Ошибка: {message[:80]}"
        if screen:
            text += f" · {screen}"
        if count > 1:
            text += f" · {count} раза" if count < 5 else f" · {count} раз"
        events.append(Event(at, EventKind.ERROR, text))

    events.sort(key=lambda e: e.at, reverse=True)
    return events[:FEED_LIMIT]


# --- Удержание ---


@dataclass(frozen=True)
class Cohort:
    # Понедельник недели, когда тренеры пришли
    start: date
    trainers: int
    # Для каждой точки из COHORT_POINTS: сколько живы через столько недель; None — рано
    alive: list[int | None]


async def cohorts(
    session: AsyncSession, now: datetime, admin_telegram_ids: Collection[int]
) -> list[Cohort]:
    today = now.astimezone(ADMIN_TIMEZONE).date()
    monday = today - timedelta(days=today.weekday())
    first = monday - timedelta(weeks=COHORT_WEEKS - 1)
    stmt = select(Trainer).where(Trainer.created_at >= local_midnight(first))
    trainers = [
        t
        for t in (await session.scalars(stmt)).all()
        if t.user.telegram_id not in admin_telegram_ids
    ]
    sessions: dict[int, list[datetime]] = {}
    rows = await session.execute(
        select(Booking.trainer_id, Booking.starts_at).where(done(local_midnight(first), now))
    )
    for trainer_id, starts_at in rows.all():
        sessions.setdefault(int(trainer_id), []).append(starts_at)

    result = []
    for offset in range(COHORT_WEEKS - 1, -1, -1):
        start = monday - timedelta(weeks=offset)
        joined = [
            t
            for t in trainers
            if start <= t.created_at.astimezone(ADMIN_TIMEZONE).date() < start + timedelta(days=7)
        ]
        alive: list[int | None] = []
        for weeks in COHORT_POINTS:
            since = local_midnight(start + timedelta(weeks=weeks))
            until = since + WINDOW
            if until > now:
                alive.append(None)
                continue
            alive.append(
                sum(1 for t in joined if any(since <= at < until for at in sessions.get(t.id, [])))
            )
        result.append(Cohort(start=start, trainers=len(joined), alive=alive))
    return result


# --- Чем пользуются ---


class Feature(StrEnum):
    PACKAGES = "packages"
    SELF_BOOKING = "self_booking"
    RESCHEDULE = "reschedule"
    NOTES = "notes"
    MEASUREMENTS = "measurements"
    RULES = "rules"


@dataclass(frozen=True)
class Usage:
    # Тренеры, у которых за 30 дней прошло хоть одно занятие: от них и считаем доли
    base: int
    features: dict[Feature, int]


async def usage(session: AsyncSession, now: datetime) -> Usage:
    since = now - USAGE_WINDOW

    async def trainers_with(column: object, *conditions: object) -> set[int]:
        stmt = select(column).where(*conditions).distinct()  # type: ignore[call-overload]
        return {int(value) for value in (await session.scalars(stmt)).all()}

    base = await trainers_with(Booking.trainer_id, done(since, now))
    features = {
        Feature.PACKAGES: await trainers_with(Package.trainer_id, Package.created_at >= since),
        Feature.SELF_BOOKING: await trainers_with(
            Booking.trainer_id, Booking.created_by == "client", Booking.created_at >= since
        ),
        Feature.RESCHEDULE: await trainers_with(
            Booking.trainer_id, Booking.rescheduled_at >= since
        ),
        Feature.NOTES: await trainers_with(
            Booking.trainer_id, Booking.trainer_note.is_not(None), Booking.starts_at >= since
        ),
        Feature.MEASUREMENTS: await trainers_with(
            TrainerClient.trainer_id,
            TrainerClient.id == ClientMeasurement.trainer_client_id,
            ClientMeasurement.created_at >= since,
        ),
        Feature.RULES: await trainers_with(Trainer.id, Trainer.rules.is_not(None)),
    }
    return Usage(base=len(base), features={key: len(ids & base) for key, ids in features.items()})


# --- Состояние ---


@dataclass(frozen=True)
class Health:
    errors_day: int
    notifications_sent_day: int
    notifications_failed_day: int


async def health(session: AsyncSession, now: datetime) -> Health:
    day_ago = now - timedelta(days=1)

    async def count(*conditions: ColumnElement[bool], of: object) -> int:
        return int(await session.scalar(select(func.count(of)).where(*conditions)) or 0)  # type: ignore[arg-type]

    return Health(
        errors_day=await count(ClientError.created_at >= day_ago, of=ClientError.id),
        notifications_sent_day=await count(
            Notification.sent_at >= day_ago, Notification.status == "sent", of=Notification.id
        ),
        notifications_failed_day=await count(
            Notification.send_at >= day_ago, Notification.status == "failed", of=Notification.id
        ),
    )
