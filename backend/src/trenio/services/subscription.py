"""Подписка тренера: пробный период, Pro и бесплатный тариф с лимитом клиентов.

Новый тренер получает trial_days дней Pro. Потом, пока не оплатит, он на бесплатном
тарифе: всё работает как раньше, но новых клиентов больше free_client_limit не добавить.
Уже добавленные клиенты, записи и блоки никуда не деваются. Админы всегда на Pro.

Цену, пробный период и лимит админ меняет в веб-админке (Terms в app_settings).
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.config import get_settings
from trenio.db.models import AppSetting, Trainer, TrainerClient, User
from trenio.services import notifications

# За сколько до конца Pro или пробного периода предупреждаем; 0 — в момент окончания
ENDING_ALERTS = (timedelta(days=3), timedelta(0))


@dataclass(frozen=True, slots=True)
class Plan:
    days: int
    price: int


@dataclass(frozen=True, slots=True)
class Terms:
    """Условия тарифов. Меняются из веб-админки, действуют сразу для всех."""

    # Цена Pro за 30 дней, в рублях
    price_month: int = 349
    trial_days: int = 30
    free_client_limit: int = 3


TERMS_KEY = "plans"


async def get_terms(session: AsyncSession) -> Terms:
    row = await session.get(AppSetting, TERMS_KEY)
    if row is None:
        return Terms()
    known = Terms.__dataclass_fields__
    return Terms(**{key: value for key, value in row.value.items() if key in known})


async def save_terms(session: AsyncSession, terms: Terms) -> None:
    """Коммит за вызывающим: вместе с записью в журнал действий."""
    row = await session.get(AppSetting, TERMS_KEY)
    if row is None:
        session.add(AppSetting(key=TERMS_KEY, value=asdict(terms)))
    else:
        row.value = asdict(terms)


def plans(terms: Terms) -> dict[str, Plan]:
    """Тарифы к оплате. Годовой (365 дней, 2 990 ₽) временно убран."""
    return {"month": Plan(days=30, price=terms.price_month)}


class State(StrEnum):
    ADMIN = "admin"
    PRO = "pro"
    TRIAL = "trial"
    FREE = "free"


@dataclass(frozen=True, slots=True)
class Subscription:
    state: State
    # Когда закончится Pro или пробный период; None — бесплатный тариф или админ
    until: datetime | None
    clients: int
    # Сколько клиентов можно; None — без ограничений
    client_limit: int | None

    @property
    def can_add_client(self) -> bool:
        return self.client_limit is None or self.clients < self.client_limit


class ClientLimitReached(Exception):
    """Бесплатный тариф: больше клиентов не добавить."""


def trial_until(now: datetime, terms: Terms) -> datetime:
    return now + timedelta(days=terms.trial_days)


def ends_at(trainer: Trainer) -> datetime | None:
    """Когда у тренера заканчивается Pro, оплаченный или пробный."""
    ends = [moment for moment in (trainer.trial_until, trainer.pro_until) if moment is not None]
    return max(ends, default=None)


def is_admin_trainer(trainer: Trainer) -> bool:
    telegram_id = trainer.user.telegram_id
    return telegram_id is not None and telegram_id in get_settings().admin_telegram_ids


def state_of(trainer: Trainer, now: datetime) -> State:
    if is_admin_trainer(trainer):
        return State.ADMIN
    if trainer.pro_until is not None and trainer.pro_until > now:
        return State.PRO
    if trainer.trial_until is not None and trainer.trial_until > now:
        return State.TRIAL
    return State.FREE


async def count_clients(session: AsyncSession, trainer: Trainer) -> int:
    """Клиенты, которые идут в лимит: и с Telegram, и без. Удалившие аккаунт не считаются."""
    count = await session.scalar(
        select(func.count())
        .select_from(TrainerClient)
        .join(User, User.id == TrainerClient.user_id)
        .where(TrainerClient.trainer_id == trainer.id, User.deleted_at.is_(None))
    )
    return count or 0


async def get_subscription(session: AsyncSession, trainer: Trainer, now: datetime) -> Subscription:
    state = state_of(trainer, now)
    return Subscription(
        state=state,
        until=ends_at(trainer) if state in (State.PRO, State.TRIAL) else None,
        clients=await count_clients(session, trainer),
        client_limit=(await get_terms(session)).free_client_limit if state is State.FREE else None,
    )


async def ensure_client_slot(session: AsyncSession, trainer: Trainer, now: datetime) -> None:
    """Проверка перед новым клиентом. Блокирует строку тренера до конца транзакции,
    чтобы два одновременных перехода по ссылке не провели четвёртого клиента."""
    if state_of(trainer, now) is not State.FREE:
        return
    await session.execute(select(Trainer.id).where(Trainer.id == trainer.id).with_for_update())
    if await count_clients(session, trainer) >= (await get_terms(session)).free_client_limit:
        raise ClientLimitReached


def extend_pro(trainer: Trainer, days: int, now: datetime) -> datetime:
    """Продлевает Pro: оплаченные дни идут после текущего Pro или пробного периода."""
    start = max(now, ends_at(trainer) or now)
    trainer.pro_until = start + timedelta(days=days)
    return trainer.pro_until


async def schedule_ending_alerts(session: AsyncSession, now: datetime) -> None:
    """Предупреждения о конце Pro и пробного периода. Повторы отсекает dedup_key."""
    horizon = now + max(ENDING_ALERTS) + timedelta(hours=1)
    ends = func.greatest(Trainer.trial_until, Trainer.pro_until)
    found = (
        await session.scalars(
            select(Trainer).where(
                Trainer.is_active.is_(True),
                ends <= horizon,
                ends > now - timedelta(days=1),
            )
        )
    ).all()
    for trainer in found:
        end = ends_at(trainer)
        if end is None or is_admin_trainer(trainer):
            continue
        for before in ENDING_ALERTS:
            at = end - before
            # Конец уже прошёл: предупреждать заранее поздно, хватит сообщения об окончании
            if before and end <= now:
                continue
            await notifications.subscription_ending(session, trainer, end, before, max(at, now))
    await session.commit()
