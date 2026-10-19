"""Админ-панель: статистика платформы, тренеры и приглашения. Только для ADMIN_TELEGRAM_IDS."""

from datetime import UTC, date, datetime, timedelta
from importlib.metadata import version
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from trenio.api.deps import CurrentUser, SessionDep, SettingsDep
from trenio.api.routes.bookings import PersonOut
from trenio.bot.setup import get_bot_username
from trenio.db.models import User
from trenio.services import admin_insights, admin_stats, avatars
from trenio.services.trainers import (
    TRAINER_INVITE_PREFIX,
    create_invite,
    get_trainer_by_id,
    is_admin,
    set_trainer_active,
)


async def current_admin(user: CurrentUser, settings: SettingsDep) -> User:
    if not is_admin(user, settings.admin_telegram_ids):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Только для админа")
    return user


CurrentAdmin = Annotated[User, Depends(current_admin)]

router = APIRouter(prefix="/admin", tags=["admin"])


class WeekOut(BaseModel):
    start: date
    new_clients: int
    new_trainers: int


class FunnelOut(BaseModel):
    # Действующие тренеры
    trainers: int
    onboarded: int
    # Есть активная услуга и рабочие часы
    set_up: int
    with_clients: int
    # Были записи за последние 7 дней
    with_bookings: int


class MoneyOut(BaseModel):
    """Деньги всей платформы за текущий месяц, без разбивки по тренерам."""

    month: str
    received: int
    received_prev: int
    packages_sold: int
    packages_amount: int


class OverviewOut(BaseModel):
    users: int
    users_seen_week: int
    users_active_today: int
    # Тренеры, которые заходили 10 из последних 14 дней
    trainers_engaged: int
    trainers: int
    trainers_active: int
    trainers_disabled: int
    clients: int
    clients_new_week: int
    clients_offline: int
    bookings_week: int
    attended_week: int
    upcoming_week: int
    invites_open: int
    notifications_sent_day: int
    notifications_failed_day: int
    version: str
    weeks: list[WeekOut]
    funnel: FunnelOut
    money: MoneyOut


@router.get("/overview")
async def get_overview(_: CurrentAdmin, session: SessionDep) -> OverviewOut:
    data = await admin_stats.overview(session, datetime.now(UTC))
    return OverviewOut(
        users=data.users,
        users_seen_week=data.users_seen_week,
        users_active_today=data.users_active_today,
        trainers_engaged=data.trainers_engaged,
        trainers=data.trainers,
        trainers_active=data.trainers_active,
        trainers_disabled=data.trainers_disabled,
        clients=data.clients,
        clients_new_week=data.clients_new_week,
        clients_offline=data.clients_offline,
        bookings_week=data.bookings_week,
        attended_week=data.attended_week,
        upcoming_week=data.upcoming_week,
        invites_open=data.invites_open,
        notifications_sent_day=data.notifications_sent_day,
        notifications_failed_day=data.notifications_failed_day,
        version=version("trenio"),
        weeks=[
            WeekOut(start=w.start, new_clients=w.new_clients, new_trainers=w.new_trainers)
            for w in data.weeks
        ],
        funnel=FunnelOut(
            trainers=data.funnel.trainers,
            onboarded=data.funnel.onboarded,
            set_up=data.funnel.set_up,
            with_clients=data.funnel.with_clients,
            with_bookings=data.funnel.with_bookings,
        ),
        money=MoneyOut(
            month=data.money.month,
            received=data.money.received,
            received_prev=data.money.received_prev,
            packages_sold=data.money.packages_sold,
            packages_amount=data.money.packages_amount,
        ),
    )


class JourneyOut(BaseModel):
    """Первые шаги тренера; None — шага ещё не было."""

    onboarded_at: datetime | None
    first_client_at: datetime | None
    first_client_booking_at: datetime | None
    first_package_at: datetime | None


class PulseOut(BaseModel):
    """По окнам в 7 дней, от старого к последнему, которое кончается сейчас."""

    # Тренеры, у которых прошло хотя бы одно занятие
    live_trainers: list[int]
    sessions: list[int]
    # Процент записей, которые клиенты сделали сами; None — записей не было
    self_booked: list[int | None]


class AttentionOut(BaseModel):
    trainer_id: int
    # not_set_up, no_clients, quiet, unmarked
    reason: str
    # Сколько дней; для unmarked — сколько занятий без отметки
    count: int


class EventOut(BaseModel):
    at: datetime
    # joined, first_client, first_client_booking, first_package, quiet, error
    kind: str
    text: str
    trainer_id: int | None


class CohortOut(BaseModel):
    start: date
    trainers: int
    # Живы через 1, 2 и 4 недели; None — ещё рано
    alive: list[int | None]


class UsageOut(BaseModel):
    base: int
    features: dict[str, int]


class HealthOut(BaseModel):
    version: str
    errors_day: int
    notifications_sent_day: int
    notifications_failed_day: int


class InsightsOut(BaseModel):
    pulse: PulseOut
    attention: list[AttentionOut]
    feed: list[EventOut]
    cohort_points: list[int]
    cohorts: list[CohortOut]
    usage: UsageOut
    health: HealthOut


@router.get("/insights")
async def get_insights(_: CurrentAdmin, session: SessionDep, settings: SettingsDep) -> InsightsOut:
    """Главный экран админки: рост, кому нужна помощь, лента, удержание, состояние."""
    now = datetime.now(UTC)
    admins = settings.admin_telegram_ids
    pulse = await admin_insights.pulse(session, now)
    first = await admin_insights.firsts(session)
    usage = await admin_insights.usage(session, now)
    health = await admin_insights.health(session, now)
    return InsightsOut(
        pulse=PulseOut(
            live_trainers=pulse.live_trainers,
            sessions=pulse.sessions,
            self_booked=pulse.self_booked,
        ),
        attention=[
            AttentionOut(trainer_id=a.trainer.id, reason=a.reason, count=a.count)
            for a in await admin_insights.attention(session, now, admins)
        ],
        feed=[
            EventOut(at=e.at, kind=e.kind, text=e.text, trainer_id=e.trainer_id)
            for e in await admin_insights.feed(session, now, first)
        ],
        cohort_points=list(admin_insights.COHORT_POINTS),
        cohorts=[
            CohortOut(start=c.start, trainers=c.trainers, alive=c.alive)
            for c in await admin_insights.cohorts(session, now, admins)
        ],
        usage=UsageOut(base=usage.base, features={str(k): v for k, v in usage.features.items()}),
        health=HealthOut(
            version=version("trenio"),
            errors_day=health.errors_day,
            notifications_sent_day=health.notifications_sent_day,
            notifications_failed_day=health.notifications_failed_day,
        ),
    )


class AdminTrainerOut(BaseModel):
    id: int
    display_name: str
    avatar_url: str | None
    user: PersonOut
    # active, quiet — нет записей две недели, not_set_up, disabled
    state: str
    is_admin: bool
    since: datetime
    timezone: str
    clients: int
    clients_new_week: int
    bookings_month: int
    attended_month: int
    services: int
    last_booking_at: datetime | None
    last_seen_at: datetime | None
    # Заходил ли в каждый из последних 14 дней, от старого к сегодняшнему
    active_days: list[bool]
    # Дней подряд
    streak: int
    # За 14 дней: записей поставил сам, занятий отметил
    bookings_created: int
    marks: int
    journey: JourneyOut


@router.get("/trainers")
async def get_trainers(
    _: CurrentAdmin, session: SessionDep, settings: SettingsDep
) -> list[AdminTrainerOut]:
    rows = await admin_stats.trainer_rows(session, datetime.now(UTC))
    first = await admin_insights.firsts(session)
    return [
        AdminTrainerOut(
            id=row.trainer.id,
            display_name=row.trainer.display_name,
            avatar_url=avatars.avatar_url(row.trainer.user),
            user=PersonOut.of(row.trainer.user),
            state=row.state,
            is_admin=is_admin(row.trainer.user, settings.admin_telegram_ids),
            since=row.trainer.created_at,
            timezone=row.trainer.timezone,
            clients=row.clients,
            clients_new_week=row.clients_new_week,
            bookings_month=row.bookings_month,
            attended_month=row.attended_month,
            services=row.services,
            last_booking_at=row.last_booking_at,
            last_seen_at=row.trainer.user.last_seen_at,
            active_days=row.active_days,
            streak=row.streak,
            bookings_created=row.bookings_created,
            marks=row.marks,
            journey=JourneyOut(
                onboarded_at=row.trainer.onboarded_at,
                first_client_at=first.client.get(row.trainer.id),
                first_client_booking_at=first.client_booking.get(row.trainer.id),
                first_package_at=first.package.get(row.trainer.id),
            ),
        )
        for row in rows
    ]


class ActiveIn(BaseModel):
    active: bool


@router.post("/trainers/{trainer_id}/active", status_code=status.HTTP_204_NO_CONTENT)
async def set_active(
    trainer_id: int, body: ActiveIn, _: CurrentAdmin, session: SessionDep, settings: SettingsDep
) -> None:
    trainer = await get_trainer_by_id(session, trainer_id)
    if trainer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Тренер не найден")
    if not body.active and is_admin(trainer.user, settings.admin_telegram_ids):
        raise HTTPException(status.HTTP_409_CONFLICT, "Админа нельзя отключить")
    await set_trainer_active(session, trainer_id, body.active)


class InviteOut(BaseModel):
    url: str
    expires_at: datetime


class OpenInviteOut(BaseModel):
    created_at: datetime
    expires_at: datetime


@router.post("/invites", status_code=status.HTTP_201_CREATED)
async def new_invite(admin: CurrentAdmin, session: SessionDep, settings: SettingsDep) -> InviteOut:
    """Одноразовая ссылка для нового тренера, как команда /invite в боте."""
    invite = await create_invite(session, admin, timedelta(days=settings.trainer_invite_ttl_days))
    username = await get_bot_username()
    return InviteOut(
        url=f"https://t.me/{username}?start={TRAINER_INVITE_PREFIX}{invite.code}",
        expires_at=invite.expires_at,
    )


@router.get("/invites")
async def list_invites(_: CurrentAdmin, session: SessionDep) -> list[OpenInviteOut]:
    invites = await admin_stats.open_invites(session, datetime.now(UTC))
    return [OpenInviteOut(created_at=i.created_at, expires_at=i.expires_at) for i in invites]
