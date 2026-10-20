"""Деньги самого Trenio: подписки тренеров, MRR и прогноз на следующий месяц.

Это не деньги тренеров от клиентов (их админка показывает только суммой по платформе),
а оплаты Pro. Админы на Pro бесплатно и в расчёт не входят.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.db.models import Bot, SubscriptionPayment, Trainer
from trenio.services.admin_stats import ADMIN_TIMEZONE, TrainerRow, TrainerState
from trenio.services.subscription import get_terms

MONTH_DAYS = 30
# Сколько месяцев на графике и насколько вперёд смотрим продления
HISTORY_MONTHS = 6
RENEWALS_AHEAD = timedelta(days=45)
RECENT_PAYMENTS = 10


class Risk(StrEnum):
    """Насколько вероятно продление: по тому, пользуется ли тренер Trenio."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class Renewal:
    trainer_id: int
    name: str
    at: datetime
    # pro — продление оплаченного, trial — первая оплата после пробного периода
    kind: str
    price: int
    risk: Risk
    reason: str


@dataclass(frozen=True, slots=True)
class PaymentRow:
    paid_at: datetime
    trainer_id: int
    name: str
    plan: str
    price: int
    bot: str | None


@dataclass(frozen=True, slots=True)
class Forecast:
    optimistic: int
    realistic: int
    cautious: int


@dataclass(frozen=True, slots=True)
class MonthTotal:
    month: date
    received: int


@dataclass(frozen=True, slots=True)
class SaasMoney:
    mrr: int
    paying: int
    trials: int
    # Средний месячный платёж платящего тренера
    arpu: int
    # Процент закончивших пробный период, кто хоть раз оплатил; None — таких ещё нет
    trial_conversion: int | None
    received_total: int
    months: list[MonthTotal]
    forecast: Forecast
    renewals: list[Renewal]
    payments: list[PaymentRow]


def _month_start(moment: datetime) -> date:
    local = moment.astimezone(ADMIN_TIMEZONE)
    return date(local.year, local.month, 1)


def _shift_month(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def _risk(row: TrainerRow | None) -> tuple[Risk, str]:
    if row is None or row.state is TrainerState.DISABLED:
        return Risk.HIGH, "отключён"
    if row.state is TrainerState.QUIET:
        return Risk.HIGH, "нет записей две недели"
    if row.state is TrainerState.NOT_SET_UP:
        return Risk.MEDIUM, "не настроил расписание"
    if row.clients == 0:
        return Risk.MEDIUM, "нет клиентов"
    return Risk.LOW, f"клиентов {row.clients}, записей за месяц {row.bookings_month}"


async def summary(
    session: AsyncSession,
    now: datetime,
    rows: Sequence[TrainerRow],
    admin_trainer_ids: Collection[int],
) -> SaasMoney:
    by_id = {row.trainer.id: row for row in rows}
    month_price = (await get_terms(session)).price_month
    paid = SubscriptionPayment.status == "paid"

    # Последний оплаченный тариф тренера: из него месячная цена для MRR
    last_paid = {
        payment.trainer_id: payment
        for payment in (
            await session.scalars(
                select(SubscriptionPayment)
                .where(paid)
                .order_by(SubscriptionPayment.trainer_id, SubscriptionPayment.paid_at)
            )
        ).all()
    }

    def monthly(trainer_id: int) -> int:
        payment = last_paid.get(trainer_id)
        if payment is None:
            # Pro продлён вручную без оплаты: считаем по обычной цене
            return month_price
        return round(payment.price * MONTH_DAYS / max(payment.days, 1))

    trainers = [
        row.trainer
        for row in rows
        if row.trainer.id not in admin_trainer_ids and row.trainer.is_active
    ]
    paying = [t for t in trainers if t.pro_until is not None and t.pro_until > now]
    trials = [
        t for t in trainers if t not in paying and t.trial_until is not None and t.trial_until > now
    ]
    mrr = sum(monthly(t.id) for t in paying)

    horizon = now + timedelta(days=MONTH_DAYS)
    renewals: list[Renewal] = []
    for trainer in paying + trials:
        is_pro = trainer in paying
        ends = trainer.pro_until if is_pro else trainer.trial_until
        assert ends is not None
        if ends > now + RENEWALS_AHEAD:
            continue
        risk, reason = _risk(by_id.get(trainer.id))
        renewals.append(
            Renewal(
                trainer_id=trainer.id,
                name=trainer.display_name,
                at=ends,
                kind="pro" if is_pro else "trial",
                price=monthly(trainer.id) if is_pro else month_price,
                risk=risk,
                reason=reason,
            )
        )
    renewals.sort(key=lambda r: r.at)

    # Прогноз MRR через месяц: кто продлит из тех, у кого Pro кончается в этом окне
    staying = sum(
        monthly(t.id) for t in paying if t.pro_until is not None and t.pro_until > horizon
    )
    due = [r for r in renewals if r.at <= horizon]
    forecast = Forecast(
        optimistic=staying + sum(r.price for r in due),
        realistic=staying + sum(r.price for r in due if r.risk is not Risk.HIGH),
        cautious=staying + sum(r.price for r in due if r.kind == "pro" and r.risk is Risk.LOW),
    )

    ended_trial = [t for t in trainers if t.trial_until is not None and t.trial_until <= now]
    converted = [t for t in ended_trial if t.id in last_paid]
    conversion = round(100 * len(converted) / len(ended_trial)) if ended_trial else None

    # Сколько пришло деньгами: часть цены могла покрыть реферальный баланс
    received = SubscriptionPayment.amount
    total = await session.scalar(select(func.coalesce(func.sum(received), 0)).where(paid))
    first_month = _shift_month(_month_start(now), -(HISTORY_MONTHS - 1))
    month_col = func.date_trunc(
        "month", func.timezone(str(ADMIN_TIMEZONE), SubscriptionPayment.paid_at)
    )
    per_month = {
        value.date(): int(amount)
        for value, amount in (
            await session.execute(
                select(month_col, func.sum(received)).where(paid).group_by(month_col)
            )
        ).all()
    }
    months = [
        MonthTotal(month=m, received=per_month.get(m, 0))
        for m in (_shift_month(first_month, i) for i in range(HISTORY_MONTHS))
    ]

    recent = await session.execute(
        select(SubscriptionPayment, Trainer.display_name, Bot.username)
        .join(Trainer, Trainer.id == SubscriptionPayment.trainer_id)
        .join(Bot, Bot.id == SubscriptionPayment.bot_id)
        .where(paid)
        .order_by(SubscriptionPayment.paid_at.desc())
        .limit(RECENT_PAYMENTS)
    )
    payments = [
        PaymentRow(
            paid_at=payment.paid_at or payment.created_at,
            trainer_id=payment.trainer_id,
            name=name,
            plan=payment.plan,
            price=payment.price,
            bot=bot,
        )
        for payment, name, bot in recent.all()
    ]

    return SaasMoney(
        mrr=mrr,
        paying=len(paying),
        trials=len(trials),
        arpu=round(mrr / len(paying)) if paying else 0,
        trial_conversion=conversion,
        received_total=int(total or 0),
        months=months,
        forecast=forecast,
        renewals=renewals,
        payments=payments,
    )
