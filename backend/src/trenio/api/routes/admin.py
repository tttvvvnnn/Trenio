"""Админ-панель: статистика платформы, тренеры и приглашения. Только для ADMIN_TELEGRAM_IDS."""

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from importlib.metadata import version
from typing import Annotated, Any

from aiogram.exceptions import TelegramAPIError
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.api.deps import SessionDep, SettingsDep, bearer, current_user
from trenio.api.routes.admin_auth import client_ip, cookie_session, current_web_admin
from trenio.api.routes.bookings import PersonOut
from trenio.bot.setup import get_bot, get_bot_username
from trenio.config import Settings
from trenio.db.models import AdminAuditEntry, PromoCode, SupportTicket, Trainer, User
from trenio.delivery.channel import DeliveryError, TelegramChannel
from trenio.delivery.kick import kick
from trenio.delivery.texts import broadcast_message
from trenio.services import (
    admin_auth,
    admin_clients,
    admin_insights,
    admin_stats,
    admin_trainer,
    avatars,
    broadcasts,
    privacy,
    promo_codes,
    saas_money,
    subscription,
    support,
)
from trenio.services.trainers import (
    TRAINER_INVITE_PREFIX,
    create_invite,
    get_trainer_by_id,
    is_admin,
    set_trainer_active,
)


@dataclass(frozen=True, slots=True)
class Admin:
    user: User
    # Вход в веб-админку; None — запрос из Mini App
    session_id: str | None
    ip: str | None

    async def audit(
        self,
        session: AsyncSession,
        action: str,
        target: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Запись в журнал действий. Коммит — вместе с самим действием."""
        await admin_auth.audit(
            session,
            self.user.id,
            action,
            session_id=self.session_id,
            target=target,
            payload=payload,
            ip=self.ip,
        )


async def current_admin(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Admin:
    """Админ из Mini App (токен в заголовке) или из веб-админки (кука и подтверждённый вход)."""
    session_id = None
    if credentials is not None:
        user = await current_user(session, settings, credentials)
    else:
        admin_session = await cookie_session(request, session, settings)
        web_admin = await current_web_admin(request, admin_session, session, settings)
        user, session_id = web_admin.user, web_admin.session.id
    if not is_admin(user, settings.admin_telegram_ids):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Только для админа")
    return Admin(user=user, session_id=session_id, ip=client_ip(request))


CurrentAdmin = Annotated[Admin, Depends(current_admin)]

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
    trial_until: datetime | None
    pro_until: datetime | None


def _trainer_out(
    row: admin_stats.TrainerRow, first: admin_insights.Firsts, settings: Settings
) -> AdminTrainerOut:
    return AdminTrainerOut(
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
        trial_until=row.trainer.trial_until,
        pro_until=row.trainer.pro_until,
    )


@router.get("/trainers")
async def get_trainers(
    _: CurrentAdmin, session: SessionDep, settings: SettingsDep
) -> list[AdminTrainerOut]:
    rows = await admin_stats.trainer_rows(session, datetime.now(UTC))
    first = await admin_insights.firsts(session)
    return [_trainer_out(row, first, settings) for row in rows]


class ActiveIn(BaseModel):
    active: bool


@router.post("/trainers/{trainer_id}/active", status_code=status.HTTP_204_NO_CONTENT)
async def set_active(
    trainer_id: int, body: ActiveIn, admin: CurrentAdmin, session: SessionDep, settings: SettingsDep
) -> None:
    trainer = await get_trainer_by_id(session, trainer_id)
    if trainer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Тренер не найден")
    if not body.active and is_admin(trainer.user, settings.admin_telegram_ids):
        raise HTTPException(status.HTTP_409_CONFLICT, "Админа нельзя отключить")
    await admin.audit(
        session,
        "trainer.enabled" if body.active else "trainer.disabled",
        target=f"trainer:{trainer_id}",
        payload={"name": trainer.display_name},
    )
    await set_trainer_active(session, trainer_id, body.active)


async def _trainer(session: AsyncSession, trainer_id: int) -> Trainer:
    trainer = await get_trainer_by_id(session, trainer_id)
    if trainer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Тренер не найден")
    return trainer


class ProIn(BaseModel):
    days: int = Field(ge=1, le=366)


class ProOut(BaseModel):
    pro_until: datetime


@router.post("/trainers/{trainer_id}/pro")
async def extend_trainer_pro(
    trainer_id: int, body: ProIn, admin: CurrentAdmin, session: SessionDep
) -> ProOut:
    """Pro в подарок: дни идут после текущего Pro или пробного периода, как при оплате."""
    trainer = await _trainer(session, trainer_id)
    until = subscription.extend_pro(trainer, body.days, datetime.now(UTC))
    await admin.audit(
        session,
        "trainer.pro_extended",
        target=f"trainer:{trainer_id}",
        payload={"name": trainer.display_name, "days": body.days, "until": until.isoformat()},
    )
    await session.commit()
    return ProOut(pro_until=until)


MESSAGE_HEADER = "Сообщение от команды Trenio\n\n"


async def send_to_trainer(telegram_id: int, text: str) -> None:
    await get_bot().send_message(telegram_id, MESSAGE_HEADER + text)


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=3500)


@router.post("/trainers/{trainer_id}/message", status_code=status.HTTP_204_NO_CONTENT)
async def message_trainer(
    trainer_id: int, body: MessageIn, admin: CurrentAdmin, session: SessionDep
) -> None:
    """Сообщение тренеру в бот от имени Trenio."""
    trainer = await _trainer(session, trainer_id)
    text = body.text.strip()
    if not text or trainer.user.telegram_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Нечего или некуда отправить")
    try:
        await send_to_trainer(trainer.user.telegram_id, text)
    except TelegramAPIError as error:
        # Чаще всего тренер остановил бота
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Telegram: {error.message}") from error
    await admin.audit(
        session,
        "trainer.messaged",
        target=f"trainer:{trainer_id}",
        payload={"name": trainer.display_name, "text": text[:500]},
    )
    await session.commit()


class DeleteTrainerIn(BaseModel):
    # Имя тренера, набранное руками: защита от удаления не того
    confirm_name: str
    reason: str


@router.post("/trainers/{trainer_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trainer(
    trainer_id: int,
    body: DeleteTrainerIn,
    admin: CurrentAdmin,
    session: SessionDep,
    settings: SettingsDep,
) -> None:
    """Удаляет тренера со всем, что он вёл: как «Удалить аккаунт» в его профиле."""
    trainer = await _trainer(session, trainer_id)
    if is_admin(trainer.user, settings.admin_telegram_ids):
        raise HTTPException(status.HTTP_409_CONFLICT, "Админа нельзя удалить")
    if body.confirm_name.strip().casefold() != trainer.display_name.strip().casefold():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Имя не совпадает")
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Укажите причину")
    clients = await subscription.count_clients(session, trainer)
    await admin.audit(
        session,
        "trainer.deleted",
        target=f"trainer:{trainer_id}",
        payload={"name": trainer.display_name, "clients": clients, "reason": reason[:500]},
    )
    await privacy.delete_account(session, trainer.user, datetime.now(UTC))


class InviteOut(BaseModel):
    url: str
    expires_at: datetime


class OpenInviteOut(BaseModel):
    created_at: datetime
    expires_at: datetime


@router.post("/invites", status_code=status.HTTP_201_CREATED)
async def new_invite(admin: CurrentAdmin, session: SessionDep, settings: SettingsDep) -> InviteOut:
    """Одноразовая ссылка для нового тренера, как команда /invite в боте."""
    await admin.audit(session, "invite.created")
    invite = await create_invite(
        session, admin.user, timedelta(days=settings.trainer_invite_ttl_days)
    )
    username = await get_bot_username()
    return InviteOut(
        url=f"https://t.me/{username}?start={TRAINER_INVITE_PREFIX}{invite.code}",
        expires_at=invite.expires_at,
    )


@router.get("/invites")
async def list_invites(_: CurrentAdmin, session: SessionDep) -> list[OpenInviteOut]:
    invites = await admin_stats.open_invites(session, datetime.now(UTC))
    return [OpenInviteOut(created_at=i.created_at, expires_at=i.expires_at) for i in invites]


class MonthTotalOut(BaseModel):
    month: date
    received: int


class ForecastOut(BaseModel):
    optimistic: int
    realistic: int
    cautious: int


class RenewalOut(BaseModel):
    trainer_id: int
    name: str
    at: datetime
    # pro или trial
    kind: str
    price: int
    # low, medium, high
    risk: str
    reason: str


class SubscriptionPaymentOut(BaseModel):
    paid_at: datetime
    trainer_id: int
    name: str
    plan: str
    price: int
    # Через какой бот пришла оплата
    bot: str | None


class SaasMoneyOut(BaseModel):
    mrr: int
    paying: int
    trials: int
    arpu: int
    trial_conversion: int | None
    received_total: int
    months: list[MonthTotalOut]
    forecast: ForecastOut
    renewals: list[RenewalOut]
    payments: list[SubscriptionPaymentOut]


@router.get("/money")
async def get_money(_: CurrentAdmin, session: SessionDep, settings: SettingsDep) -> SaasMoneyOut:
    """Подписки Trenio: MRR, прогноз на месяц вперёд, ближайшие продления и оплаты."""
    now = datetime.now(UTC)
    rows = await admin_stats.trainer_rows(session, now)
    admins = {
        row.trainer.id for row in rows if is_admin(row.trainer.user, settings.admin_telegram_ids)
    }
    data = await saas_money.summary(session, now, rows, admins)
    return SaasMoneyOut(
        mrr=data.mrr,
        paying=data.paying,
        trials=data.trials,
        arpu=data.arpu,
        trial_conversion=data.trial_conversion,
        received_total=data.received_total,
        months=[MonthTotalOut(month=m.month, received=m.received) for m in data.months],
        forecast=ForecastOut(
            optimistic=data.forecast.optimistic,
            realistic=data.forecast.realistic,
            cautious=data.forecast.cautious,
        ),
        renewals=[
            RenewalOut(
                trainer_id=r.trainer_id,
                name=r.name,
                at=r.at,
                kind=r.kind,
                price=r.price,
                risk=r.risk.value,
                reason=r.reason,
            )
            for r in data.renewals
        ],
        payments=[
            SubscriptionPaymentOut(
                paid_at=p.paid_at,
                trainer_id=p.trainer_id,
                name=p.name,
                plan=p.plan,
                price=p.price,
                bot=p.bot,
            )
            for p in data.payments
        ],
    )


class TrainerRefOut(BaseModel):
    id: int
    name: str


class AdminClientOut(BaseModel):
    id: int
    first_name: str
    last_name: str | None
    username: str | None
    avatar_url: str | None
    # Клиент без Telegram: его завёл тренер
    offline: bool
    deleted: bool
    trainers: list[TrainerRefOut]
    since: datetime
    bookings: int
    attended: int
    last_booking_at: datetime | None
    next_booking_at: datetime | None
    last_seen_at: datetime | None
    active_days: int

    @classmethod
    def of(cls, row: admin_clients.ClientRow) -> "AdminClientOut":
        user = row.user
        return cls(
            id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username,
            avatar_url=avatars.avatar_url(user),
            offline=user.is_offline and not user.is_deleted,
            deleted=user.is_deleted,
            trainers=[TrainerRefOut(id=t.id, name=t.name) for t in row.trainers],
            since=row.since,
            bookings=row.bookings,
            attended=row.attended,
            last_booking_at=row.last_booking_at,
            next_booking_at=row.next_booking_at,
            last_seen_at=user.last_seen_at,
            active_days=row.active_days,
        )


class ClientLinkOut(BaseModel):
    trainer: TrainerRefOut
    since: datetime
    bookings: int
    attended: int
    missed: int
    cancelled: int
    open_packages: int
    last_booking_at: datetime | None
    next_booking_at: datetime | None


class ClientHistoryOut(BaseModel):
    starts_at: datetime
    trainer: str
    service: str
    status: str
    attendance: str | None
    # client — записался сам, trainer — записал тренер
    created_by: str


class ClientCardOut(BaseModel):
    client: AdminClientOut
    telegram_id: int | None
    # Человек ещё и тренер: такого удаляют вместе с данными тренера, не отсюда
    is_trainer: bool
    links: list[ClientLinkOut]
    history: list[ClientHistoryOut]
    activity: list[bool]


class ClientPageOut(BaseModel):
    items: list[AdminClientOut]
    total: int
    page_size: int


@router.get("/clients")
async def get_clients(
    _: CurrentAdmin,
    session: SessionDep,
    q: str = "",
    deleted: bool = False,
    trainer_id: int | None = None,
    sort: admin_clients.Sort = admin_clients.Sort.NEW,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ClientPageOut:
    page = await admin_clients.search(
        session,
        q[:64],
        datetime.now(UTC),
        deleted=deleted,
        trainer_id=trainer_id,
        sort=sort,
        offset=offset,
    )
    return ClientPageOut(
        items=[AdminClientOut.of(row) for row in page.rows],
        total=page.total,
        page_size=admin_clients.PAGE_SIZE,
    )


async def _card(session: AsyncSession, user_id: int) -> admin_clients.ClientCard:
    data = await admin_clients.card(session, user_id, datetime.now(UTC))
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Клиент не найден")
    return data


@router.get("/clients/{user_id}")
async def get_client(user_id: int, _: CurrentAdmin, session: SessionDep) -> ClientCardOut:
    data = await _card(session, user_id)
    return ClientCardOut(
        client=AdminClientOut.of(data.row),
        telegram_id=data.row.user.telegram_id,
        is_trainer=data.is_trainer,
        links=[
            ClientLinkOut(
                trainer=TrainerRefOut(id=link.trainer.id, name=link.trainer.name),
                since=link.since,
                bookings=link.bookings,
                attended=link.attended,
                missed=link.missed,
                cancelled=link.cancelled,
                open_packages=link.open_packages,
                last_booking_at=link.last_booking_at,
                next_booking_at=link.next_booking_at,
            )
            for link in data.links
        ],
        history=[
            ClientHistoryOut(
                starts_at=h.starts_at,
                trainer=h.trainer,
                service=h.service,
                status=h.status,
                attendance=h.attendance,
                created_by=h.created_by,
            )
            for h in data.history
        ],
        activity=data.activity,
    )


class DeleteClientIn(BaseModel):
    # Откуда пришёл запрос на удаление: «письмо на почту 20.10», для журнала
    reason: str


@router.post("/clients/{user_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    user_id: int,
    body: DeleteClientIn,
    admin: CurrentAdmin,
    session: SessionDep,
    settings: SettingsDep,
) -> None:
    """Удаление данных по запросу клиента: то же, что «Удалить аккаунт» в его профиле."""
    data = await _card(session, user_id)
    user = data.row.user
    if user.is_deleted:
        raise HTTPException(status.HTTP_409_CONFLICT, "Аккаунт уже удалён")
    if data.is_trainer or is_admin(user, settings.admin_telegram_ids):
        raise HTTPException(status.HTTP_409_CONFLICT, "Это тренер: его так не удалить")
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Укажите, откуда запрос")
    await admin.audit(
        session,
        "client.deleted",
        target=f"user:{user.id}",
        payload={
            "name": " ".join(filter(None, [user.first_name, user.last_name])),
            "trainers": [t.name for t in data.row.trainers],
            "reason": reason[:500],
        },
    )
    await privacy.delete_account(session, user, datetime.now(UTC))


class TermsIO(BaseModel):
    price_month: int = Field(ge=1, le=100_000)
    trial_days: int = Field(ge=0, le=365)
    free_client_limit: int = Field(ge=0, le=1000)


@router.get("/plans")
async def get_plans(_: CurrentAdmin, session: SessionDep) -> TermsIO:
    terms = await subscription.get_terms(session)
    return TermsIO(**asdict(terms))


@router.put("/plans")
async def set_plans(body: TermsIO, admin: CurrentAdmin, session: SessionDep) -> TermsIO:
    """Цена Pro, пробный период и лимит бесплатного тарифа. Действует сразу.

    Пробный период меняется только у новых тренеров: уже выданный не пересчитываем.
    """
    before = await subscription.get_terms(session)
    after = subscription.Terms(**body.model_dump())
    await subscription.save_terms(session, after)
    await admin.audit(
        session, "plans.updated", payload={"before": asdict(before), "after": asdict(after)}
    )
    await session.commit()
    return body


class AudienceOut(BaseModel):
    count: int
    names: list[str]


@router.get("/broadcasts/audience")
async def get_audience(
    segment: broadcasts.Segment, _: CurrentAdmin, session: SessionDep
) -> AudienceOut:
    trainers = await broadcasts.audience(session, segment, datetime.now(UTC))
    return AudienceOut(count=len(trainers), names=[t.display_name for t in trainers])


class BroadcastIn(BaseModel):
    text: str = Field(min_length=1, max_length=3500)
    with_button: bool = True


class NewBroadcastIn(BroadcastIn):
    segment: broadcasts.Segment


class BroadcastOut(BaseModel):
    id: int
    text: str
    segment: str
    with_button: bool
    recipients: int
    sent: int
    failed: int
    pending: int
    created_at: datetime


def _text(body: BroadcastIn) -> str:
    text = body.text.strip()
    if not text:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Пустое сообщение")
    return text


async def send_test(user: User, text: str, with_button: bool) -> None:
    await TelegramChannel().send(user, broadcast_message(text, with_button))


@router.post("/broadcasts/test", status_code=status.HTTP_204_NO_CONTENT)
async def test_broadcast(body: BroadcastIn, admin: CurrentAdmin) -> None:
    """Пробная отправка себе: посмотреть, как сообщение выглядит в Telegram."""
    try:
        await send_test(admin.user, _text(body), body.with_button)
    except DeliveryError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Telegram: {error}") from error


@router.post("/broadcasts", status_code=status.HTTP_201_CREATED)
async def new_broadcast(
    body: NewBroadcastIn, admin: CurrentAdmin, session: SessionDep
) -> BroadcastOut:
    now = datetime.now(UTC)
    text = _text(body)
    item = await broadcasts.send(session, text, body.segment, body.with_button, admin.user.id, now)
    if item.recipients == 0:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "В этом сегменте никого нет")
    await admin.audit(
        session,
        "broadcast.sent",
        target=f"broadcast:{item.id}",
        payload={"segment": body.segment.value, "recipients": item.recipients, "text": text[:500]},
    )
    await session.commit()
    kick()
    return BroadcastOut(
        id=item.id,
        text=item.text,
        segment=item.segment,
        with_button=item.with_button,
        recipients=item.recipients,
        sent=0,
        failed=0,
        pending=item.recipients,
        created_at=item.created_at,
    )


@router.get("/broadcasts")
async def list_broadcasts(_: CurrentAdmin, session: SessionDep) -> list[BroadcastOut]:
    return [
        BroadcastOut(
            id=d.broadcast.id,
            text=d.broadcast.text,
            segment=d.broadcast.segment,
            with_button=d.broadcast.with_button,
            recipients=d.broadcast.recipients,
            sent=d.sent,
            failed=d.failed,
            pending=d.pending,
            created_at=d.broadcast.created_at,
        )
        for d in await broadcasts.history(session)
    ]


AUDIT_LIMIT = 100


class AuditOut(BaseModel):
    id: int
    action: str
    target: str | None
    payload: dict[str, Any]
    ip: str | None
    # Из Mini App или из веб-админки
    web: bool
    created_at: datetime


@router.get("/audit")
async def get_audit(_: CurrentAdmin, session: SessionDep) -> list[AuditOut]:
    """Последние записи журнала действий, свежие сверху."""
    rows = await session.scalars(
        select(AdminAuditEntry).order_by(AdminAuditEntry.id.desc()).limit(AUDIT_LIMIT)
    )
    return [
        AuditOut(
            id=row.id,
            action=row.action,
            target=row.target,
            payload=row.payload,
            ip=row.ip,
            web=row.session_id is not None,
            created_at=row.created_at,
        )
        for row in rows
    ]


class PromoCodeIn(BaseModel):
    code: str = Field(pattern=r"^\s*[A-Za-zА-Яа-яЁё0-9_-]{3,32}\s*$")
    kind: promo_codes.Kind
    value: int = Field(ge=1, le=100_000)
    max_uses: int | None = Field(default=None, ge=1, le=100_000)
    expires_at: datetime | None = None
    note: str | None = Field(default=None, max_length=200)


class PromoCodeOut(BaseModel):
    id: int
    code: str
    kind: str
    value: int
    max_uses: int | None
    expires_at: datetime | None
    note: str | None
    is_active: bool
    created_at: datetime
    # Дни Pro выданы или скидка потрачена на оплату
    used: int
    # Скидка введена, но оплаты ещё не было
    reserved: int

    @classmethod
    def of(cls, code: PromoCode, used: int = 0, reserved: int = 0) -> "PromoCodeOut":
        return cls(
            id=code.id,
            code=code.code,
            kind=code.kind,
            value=code.value,
            max_uses=code.max_uses,
            expires_at=code.expires_at,
            note=code.note,
            is_active=code.is_active,
            created_at=code.created_at,
            used=used,
            reserved=reserved,
        )


@router.get("/promo-codes")
async def list_promo_codes(_: CurrentAdmin, session: SessionDep) -> list[PromoCodeOut]:
    return [
        PromoCodeOut.of(row.code, row.used, row.reserved)
        for row in await promo_codes.list_codes(session)
    ]


@router.post("/promo-codes", status_code=status.HTTP_201_CREATED)
async def create_promo_code(
    body: PromoCodeIn, admin: CurrentAdmin, session: SessionDep
) -> PromoCodeOut:
    if body.kind is promo_codes.Kind.PERCENT and body.value > 99:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Скидка больше 99%")
    if body.kind is promo_codes.Kind.DAYS and body.value > 366:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Больше года Pro")
    code = promo_codes.normalize(body.code)
    if await session.scalar(select(PromoCode.id).where(PromoCode.code == code)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Такой код уже есть")
    item = PromoCode(
        code=code,
        kind=body.kind.value,
        value=body.value,
        max_uses=body.max_uses,
        expires_at=body.expires_at,
        note=(body.note or "").strip() or None,
        created_at=datetime.now(UTC),
    )
    session.add(item)
    await session.flush()
    await admin.audit(
        session,
        "promo_code.created",
        target=f"promo_code:{item.id}",
        payload={"code": code, "kind": item.kind, "value": item.value},
    )
    await session.commit()
    return PromoCodeOut.of(item)


@router.post("/promo-codes/{code_id}/active", status_code=status.HTTP_204_NO_CONTENT)
async def set_promo_code_active(
    code_id: int, body: ActiveIn, admin: CurrentAdmin, session: SessionDep
) -> None:
    """Выключенный код больше не принимается; уже введённые скидки остаются за тренерами."""
    item = await session.get(PromoCode, code_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Промокод не найден")
    item.is_active = body.active
    await admin.audit(
        session,
        "promo_code.enabled" if body.active else "promo_code.disabled",
        target=f"promo_code:{code_id}",
        payload={"code": item.code},
    )
    await session.commit()


class RedemptionOut(BaseModel):
    trainer_id: int
    name: str
    status: str
    created_at: datetime
    used_at: datetime | None


@router.get("/promo-codes/{code_id}/redemptions")
async def get_redemptions(
    code_id: int, _: CurrentAdmin, session: SessionDep
) -> list[RedemptionOut]:
    return [
        RedemptionOut(
            trainer_id=row.trainer_id,
            name=name,
            status=row.status,
            created_at=row.created_at,
            used_at=row.used_at,
        )
        for row, name in await promo_codes.redemptions(session, code_id)
    ]


class TicketOut(BaseModel):
    id: int
    trainer_id: int
    trainer_name: str
    username: str | None
    kind: str
    text: str
    rating: int | None
    status: str
    answer: str | None
    answered_at: datetime | None
    created_at: datetime

    @classmethod
    def of(cls, ticket: SupportTicket) -> "TicketOut":
        return cls(
            id=ticket.id,
            trainer_id=ticket.trainer_id,
            trainer_name=ticket.trainer.display_name,
            username=ticket.trainer.user.username,
            kind=ticket.kind,
            text=ticket.text,
            rating=ticket.rating,
            status=ticket.status,
            answer=ticket.answer,
            answered_at=ticket.answered_at,
            created_at=ticket.created_at,
        )


@router.get("/support")
async def list_support(
    _: CurrentAdmin,
    session: SessionDep,
    status_: Annotated[support.Status | None, Query(alias="status")] = None,
) -> list[TicketOut]:
    return [TicketOut.of(ticket) for ticket in await support.for_admin(session, status_)]


async def _ticket(session: AsyncSession, ticket_id: int) -> SupportTicket:
    ticket = await session.get(SupportTicket, ticket_id)
    if ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Обращение не найдено")
    return ticket


async def send_answer(telegram_id: int, text: str) -> None:
    await get_bot().send_message(telegram_id, text)


class AnswerIn(BaseModel):
    text: str = Field(min_length=1, max_length=3500)


@router.post("/support/{ticket_id}/answer")
async def answer_support(
    ticket_id: int, body: AnswerIn, admin: CurrentAdmin, session: SessionDep
) -> TicketOut:
    """Ответ уходит тренеру в бот. Можно ответить ещё раз: в карточке останется последний."""
    ticket = await _ticket(session, ticket_id)
    text = body.text.strip()
    telegram_id = ticket.trainer.user.telegram_id
    if not text or telegram_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Нечего или некуда отправить")
    try:
        await send_answer(telegram_id, support.answer_message(ticket, text))
    except TelegramAPIError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Telegram: {error.message}") from error
    ticket.answer = text
    ticket.answered_at = datetime.now(UTC)
    ticket.status = support.Status.ANSWERED.value
    await admin.audit(
        session,
        "support.answered",
        target=f"support:{ticket_id}",
        payload={"name": ticket.trainer.display_name, "text": text[:500]},
    )
    await session.commit()
    return TicketOut.of(ticket)


class TicketStatusIn(BaseModel):
    closed: bool


@router.post("/support/{ticket_id}/status")
async def set_support_status(
    ticket_id: int, body: TicketStatusIn, admin: CurrentAdmin, session: SessionDep
) -> TicketOut:
    """Закрыть без ответа (отзыв, спам) или вернуть в работу."""
    ticket = await _ticket(session, ticket_id)
    if body.closed:
        ticket.status = support.Status.CLOSED.value
    else:
        ticket.status = (support.Status.ANSWERED if ticket.answer else support.Status.NEW).value
    await admin.audit(
        session,
        "support.closed" if body.closed else "support.reopened",
        target=f"support:{ticket_id}",
        payload={"name": ticket.trainer.display_name},
    )
    await session.commit()
    return TicketOut.of(ticket)


class ServiceOut(BaseModel):
    name: str
    duration_min: int
    capacity: int
    is_active: bool


class HoursOut(BaseModel):
    weekday: int
    start: str
    end: str


class TrainerPaymentOut(BaseModel):
    created_at: datetime
    paid_at: datetime | None
    plan: str
    days: int
    price: int
    # Сколько деньгами и сколько с баланса
    amount: int
    balance_used: int
    # pending, paid, canceled
    status: str


class TrainerPromoOut(BaseModel):
    code_id: int
    code: str
    kind: str
    value: int
    # reserved — скидка ждёт оплаты, used — применён
    status: str
    created_at: datetime
    used_at: datetime | None


class TrainerProfileOut(BaseModel):
    trainer: AdminTrainerOut
    telegram_id: int | None
    address: str | None
    auto_confirm: bool
    cancel_hours: int
    balance: int
    referred_by: TrainerRefOut | None
    referrals: list[TrainerRefOut]
    # Заходил ли в каждый из последних 30 дней, от старого к сегодняшнему
    activity: list[bool]
    services: list[ServiceOut]
    hours: list[HoursOut]
    paid_total: int
    payments: list[TrainerPaymentOut]
    promos: list[TrainerPromoOut]
    tickets: list[TicketOut]
    audit: list[AuditOut]


@router.get("/trainers/{trainer_id}")
async def get_trainer_profile(
    trainer_id: int, _: CurrentAdmin, session: SessionDep, settings: SettingsDep
) -> TrainerProfileOut:
    """Всё о тренере на одной странице. Клиенты — отдельно: /admin/clients?trainer_id=."""
    trainer = await _trainer(session, trainer_id)
    now = datetime.now(UTC)
    row = next(
        r for r in await admin_stats.trainer_rows(session, now) if r.trainer.id == trainer_id
    )
    data = await admin_trainer.profile(session, trainer, now)
    return TrainerProfileOut(
        trainer=_trainer_out(row, await admin_insights.firsts(session), settings),
        telegram_id=trainer.user.telegram_id,
        address=trainer.address,
        auto_confirm=trainer.auto_confirm,
        cancel_hours=trainer.cancel_hours,
        balance=trainer.balance,
        referred_by=(
            TrainerRefOut(id=data.referred_by.id, name=data.referred_by.name)
            if data.referred_by
            else None
        ),
        referrals=[TrainerRefOut(id=r.id, name=r.name) for r in data.referrals],
        activity=data.activity,
        services=[
            ServiceOut(
                name=s.name, duration_min=s.duration_min, capacity=s.capacity, is_active=s.is_active
            )
            for s in data.services
        ],
        hours=[
            HoursOut(
                weekday=h.weekday, start=h.start.strftime("%H:%M"), end=h.end.strftime("%H:%M")
            )
            for h in data.hours
        ],
        paid_total=data.paid_total,
        payments=[
            TrainerPaymentOut(
                created_at=p.created_at,
                paid_at=p.paid_at,
                plan=p.plan,
                days=p.days,
                price=p.price,
                amount=p.amount,
                balance_used=p.balance_used,
                status=p.status,
            )
            for p in data.payments
        ],
        promos=[
            TrainerPromoOut(
                code_id=r.code_id,
                code=r.code.code,
                kind=r.code.kind,
                value=r.code.value,
                status=r.status,
                created_at=r.created_at,
                used_at=r.used_at,
            )
            for r in data.promos
        ],
        tickets=[TicketOut.of(t) for t in data.tickets],
        audit=[
            AuditOut(
                id=a.id,
                action=a.action,
                target=a.target,
                payload=a.payload,
                ip=a.ip,
                web=a.session_id is not None,
                created_at=a.created_at,
            )
            for a in data.audit
        ],
    )
