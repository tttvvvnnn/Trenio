"""Оплата Pro и баланс тренера.

Часть цены покрывает баланс (20% с оплат приглашённых тренеров), остальное тренер платит
по СБП через Platega. Списанное с баланса возвращается, если оплата не прошла.
Подтверждение приходит callback-ом от Platega или находится опросом статуса;
в обоих случаях статус перепроверяется через API Platega и применяется один раз.
"""

import logging
from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.config import get_settings
from trenio.db.models import BalanceEntry, SubscriptionPayment, Trainer
from trenio.delivery.kick import kick
from trenio.services import notifications, platega, promo_codes, subscription

logger = logging.getLogger(__name__)

# Сколько процентов с каждой оплаты приглашённого получает пригласивший
REFERRAL_PERCENT = 20
# Меньше Platega не принимает: баланс списываем так, чтобы к оплате осталось не меньше
MIN_PAYMENT = 50
# Сколько ждём оплату по СБП, прежде чем отменить платёж и вернуть баланс
PAYMENT_TTL = timedelta(hours=24)


class PaymentUnavailable(Exception):
    """Оплата выключена или Platega не ответила."""


class UnknownPlan(ValueError):
    pass


def split_price(price: int, balance: int) -> tuple[int, int]:
    """(сколько списать с баланса, сколько заплатить деньгами)."""
    if balance >= price:
        return price, 0
    used = max(0, min(balance, price - MIN_PAYMENT))
    return used, price - used


async def _locked_trainer(session: AsyncSession, trainer_id: int) -> Trainer:
    trainer = await session.scalar(
        select(Trainer)
        .where(Trainer.id == trainer_id)
        .with_for_update(of=Trainer)
        .execution_options(populate_existing=True)
    )
    assert trainer is not None
    return trainer


def _move_balance(
    session: AsyncSession,
    trainer: Trainer,
    amount: int,
    kind: str,
    payment: SubscriptionPayment | None = None,
    from_trainer: Trainer | None = None,
) -> None:
    trainer.balance += amount
    session.add(
        BalanceEntry(
            trainer_id=trainer.id,
            amount=amount,
            kind=kind,
            payment_id=payment.id if payment is not None else None,
            from_trainer_id=from_trainer.id if from_trainer is not None else None,
        )
    )


async def price_for(session: AsyncSession, trainer: Trainer, price: int) -> int:
    """Цена тарифа для этого тренера: со скидкой по введённому промокоду, если она есть."""
    pending = await promo_codes.pending_discount(session, trainer)
    return price if pending is None else promo_codes.discounted(price, pending.code)


async def start_payment(
    session: AsyncSession, trainer: Trainer, plan_key: str, return_url: str, now: datetime
) -> SubscriptionPayment:
    """Создаёт оплату тарифа. Если всё покрыл баланс, Pro продлевается сразу."""
    plan = subscription.plans(await subscription.get_terms(session)).get(plan_key)
    if plan is None:
        raise UnknownPlan(plan_key)
    locked = await _locked_trainer(session, trainer.id)
    price = await price_for(session, locked, plan.price)
    used, amount = split_price(price, locked.balance)
    if amount and not _payments_enabled():
        await session.commit()
        raise PaymentUnavailable
    payment = SubscriptionPayment(
        trainer_id=locked.id,
        plan=plan_key,
        days=plan.days,
        price=price,
        amount=amount,
        balance_used=used,
    )
    session.add(payment)
    await session.flush()
    await promo_codes.attach(session, locked, payment)
    if used:
        _move_balance(session, locked, -used, "payment", payment)
    await session.commit()
    if amount == 0:
        await confirm(session, payment.id, now)
        await session.refresh(payment)
        return payment

    description = f"Trenio Pro на {'год' if plan_key == 'year' else 'месяц'}"
    try:
        created = await platega.create_payment(
            amount, f"trenio_{payment.id}", description, return_url
        )
    except platega.PlategaError:
        logger.exception("Platega create_payment failed for payment %s", payment.id)
        await cancel(session, payment.id)
        raise PaymentUnavailable from None
    payment.transaction_id = created.transaction_id
    payment.redirect_url = created.redirect_url
    await session.commit()
    return payment


def _payments_enabled() -> bool:
    return get_settings().payments_enabled


async def _locked_payment(session: AsyncSession, payment_id: int) -> SubscriptionPayment | None:
    return await session.scalar(
        select(SubscriptionPayment)
        .where(SubscriptionPayment.id == payment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def confirm(session: AsyncSession, payment_id: int, now: datetime) -> None:
    """Оплата прошла: продлеваем Pro и начисляем пригласившему. Повторный вызов ничего не делает."""
    payment = await _locked_payment(session, payment_id)
    if payment is None or payment.status != "pending":
        await session.commit()
        return
    payment.status = "paid"
    payment.paid_at = now
    await promo_codes.settle(session, payment, now)
    trainer = await _locked_trainer(session, payment.trainer_id)
    subscription.extend_pro(trainer, payment.days, now)
    await notifications.subscription_paid(session, trainer, payment, now)
    if payment.amount and trainer.referred_by_id is not None:
        inviter = await _locked_trainer(session, trainer.referred_by_id)
        bonus = payment.amount * REFERRAL_PERCENT // 100
        if inviter.is_active and bonus > 0:
            _move_balance(session, inviter, bonus, "referral", payment, from_trainer=trainer)
            await notifications.referral_bonus(session, inviter, payment, bonus, now)
    await session.commit()
    kick()


async def cancel(session: AsyncSession, payment_id: int) -> None:
    """Оплата не прошла: возвращаем списанное с баланса."""
    payment = await _locked_payment(session, payment_id)
    if payment is None or payment.status != "pending":
        await session.commit()
        return
    payment.status = "canceled"
    if payment.balance_used:
        trainer = await _locked_trainer(session, payment.trainer_id)
        _move_balance(session, trainer, payment.balance_used, "refund", payment)
    await session.commit()


async def refresh(session: AsyncSession, payment: SubscriptionPayment, now: datetime) -> None:
    """Спрашивает у Platega статус ожидающей оплаты и применяет его."""
    if payment.status != "pending" or payment.transaction_id is None:
        return
    try:
        status = await platega.get_status(payment.transaction_id)
    except platega.PlategaError:
        logger.warning("Platega status check failed for payment %s", payment.id)
        return
    if status == platega.CONFIRMED:
        await confirm(session, payment.id, now)
    elif status in platega.FAILED or payment.created_at < now - PAYMENT_TTL:
        await cancel(session, payment.id)
    await session.refresh(payment)


async def refresh_by_transaction(session: AsyncSession, transaction_id: str, now: datetime) -> None:
    payment = await session.scalar(
        select(SubscriptionPayment).where(SubscriptionPayment.transaction_id == transaction_id)
    )
    if payment is None:
        logger.warning("Platega callback for unknown transaction %s", transaction_id)
        return
    await refresh(session, payment, now)


async def sweep_pending(session: AsyncSession, now: datetime) -> None:
    """Опрос ожидающих оплат: на случай, если callback от Platega не дошёл."""
    pending = (
        await session.scalars(
            select(SubscriptionPayment).where(SubscriptionPayment.status == "pending")
        )
    ).all()
    for payment in pending:
        if payment.transaction_id is None:
            # Platega так и не создала платёж: сервис упал посередине
            if payment.created_at < now - timedelta(hours=1):
                await cancel(session, payment.id)
            continue
        await refresh(session, payment, now)


async def get_payment(
    session: AsyncSession, trainer: Trainer, payment_id: int
) -> SubscriptionPayment | None:
    return await session.scalar(
        select(SubscriptionPayment).where(
            SubscriptionPayment.id == payment_id, SubscriptionPayment.trainer_id == trainer.id
        )
    )


async def referral_earnings(session: AsyncSession, inviter: Trainer) -> dict[int, int]:
    """Сколько рублей принёс каждый приглашённый: from_trainer_id → сумма."""
    rows = await session.execute(
        select(BalanceEntry.from_trainer_id, func.sum(BalanceEntry.amount))
        .where(
            BalanceEntry.trainer_id == inviter.id,
            BalanceEntry.kind == "referral",
            BalanceEntry.from_trainer_id.is_not(None),
        )
        .group_by(BalanceEntry.from_trainer_id)
    )
    return {trainer_id: int(total) for trainer_id, total in rows if trainer_id}


async def paid_trainers(session: AsyncSession, ids: Sequence[int]) -> set[int]:
    """Кто из тренеров хоть раз платил деньгами."""
    if not ids:
        return set()
    rows = await session.scalars(
        select(SubscriptionPayment.trainer_id).where(
            SubscriptionPayment.trainer_id.in_(ids),
            SubscriptionPayment.status == "paid",
            SubscriptionPayment.amount > 0,
        )
    )
    return set(rows)
