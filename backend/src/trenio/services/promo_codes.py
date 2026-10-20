"""Промокоды тренеров: скидка на одну оплату Pro или дни Pro без оплаты.

Тренер вводит код на экране «Подписка». Дни Pro добавляются сразу. Скидка ждёт оплаты:
она видна в цене тарифа и тратится, когда оплата прошла. Если оплата сорвалась, скидка
остаётся за тренером. Один тренер использует каждый код один раз, лимит кода считает
тренеров, которые его ввели.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.db.models import PromoCode, PromoRedemption, SubscriptionPayment, Trainer
from trenio.services import subscription


class Kind(StrEnum):
    PERCENT = "percent"
    RUBLES = "rubles"
    DAYS = "days"


class Status(StrEnum):
    RESERVED = "reserved"
    USED = "used"


class CodeError(StrEnum):
    NOT_FOUND = "not_found"
    EXPIRED = "expired"
    EXHAUSTED = "exhausted"
    ALREADY_USED = "already_used"


ERROR_TEXT = {
    CodeError.NOT_FOUND: "Такого промокода нет",
    CodeError.EXPIRED: "Срок промокода закончился",
    CodeError.EXHAUSTED: "Промокод уже использовали все, кому он предназначался",
    CodeError.ALREADY_USED: "Вы уже вводили этот промокод",
}


class CodeRejected(Exception):
    def __init__(self, reason: CodeError) -> None:
        super().__init__(reason.value)
        self.reason = reason


def normalize(code: str) -> str:
    return code.strip().upper()


def discounted(price: int, code: PromoCode) -> int:
    """Цена со скидкой; не меньше рубля, бесплатно бывает только по коду на дни."""
    if code.kind == Kind.PERCENT:
        price -= price * code.value // 100
    elif code.kind == Kind.RUBLES:
        price -= code.value
    return max(price, 1)


async def uses(session: AsyncSession, code_id: int) -> int:
    count = await session.scalar(
        select(func.count()).select_from(PromoRedemption).where(PromoRedemption.code_id == code_id)
    )
    return count or 0


async def pending_discount(session: AsyncSession, trainer: Trainer) -> PromoRedemption | None:
    """Скидка, которая применится к следующей оплате; последняя введённая."""
    return await session.scalar(
        select(PromoRedemption)
        .where(
            PromoRedemption.trainer_id == trainer.id,
            PromoRedemption.status == Status.RESERVED,
        )
        .order_by(PromoRedemption.created_at.desc())
        .limit(1)
    )


async def redeem(
    session: AsyncSession, trainer: Trainer, raw_code: str, now: datetime
) -> PromoRedemption:
    """Тренер ввёл код. Коммит здесь: строка кода блокируется, чтобы лимит не превысили."""
    code = await session.scalar(
        select(PromoCode)
        .where(PromoCode.code == normalize(raw_code), PromoCode.is_active.is_(True))
        .with_for_update()
    )
    if code is None:
        raise CodeRejected(CodeError.NOT_FOUND)
    if code.expires_at is not None and code.expires_at <= now:
        raise CodeRejected(CodeError.EXPIRED)
    taken = await session.scalar(
        select(PromoRedemption.id).where(
            PromoRedemption.code_id == code.id, PromoRedemption.trainer_id == trainer.id
        )
    )
    if taken is not None:
        raise CodeRejected(CodeError.ALREADY_USED)
    if code.max_uses is not None and await uses(session, code.id) >= code.max_uses:
        raise CodeRejected(CodeError.EXHAUSTED)

    redemption = PromoRedemption(code_id=code.id, trainer_id=trainer.id, created_at=now)
    if code.kind == Kind.DAYS:
        subscription.extend_pro(trainer, code.value, now)
        redemption.status = Status.USED
        redemption.used_at = now
    else:
        # Новая скидка заменяет прежнюю неиспользованную: двух скидок на оплату не бывает
        previous = await pending_discount(session, trainer)
        if previous is not None:
            await session.delete(previous)
        redemption.status = Status.RESERVED
    session.add(redemption)
    await session.commit()
    await session.refresh(redemption)
    return redemption


async def attach(session: AsyncSession, trainer: Trainer, payment: SubscriptionPayment) -> None:
    """Скидка уходит в эту оплату; потратится, когда оплата пройдёт."""
    pending = await pending_discount(session, trainer)
    if pending is not None:
        pending.payment_id = payment.id


async def settle(session: AsyncSession, payment: SubscriptionPayment, now: datetime) -> None:
    """Оплата прошла: скидка использована. Коммит за вызывающим."""
    row = await session.scalar(
        select(PromoRedemption).where(
            PromoRedemption.payment_id == payment.id,
            PromoRedemption.status == Status.RESERVED,
        )
    )
    if row is not None:
        row.status = Status.USED
        row.used_at = now


@dataclass(frozen=True, slots=True)
class CodeRow:
    code: PromoCode
    used: int
    reserved: int


async def list_codes(session: AsyncSession) -> list[CodeRow]:
    codes: Sequence[PromoCode] = (
        await session.scalars(select(PromoCode).order_by(PromoCode.created_at.desc()))
    ).all()
    counts: dict[tuple[int, str], int] = {
        (code_id, status): count
        for code_id, status, count in (
            await session.execute(
                select(PromoRedemption.code_id, PromoRedemption.status, func.count()).group_by(
                    PromoRedemption.code_id, PromoRedemption.status
                )
            )
        ).all()
    }
    return [
        CodeRow(
            code=code,
            used=counts.get((code.id, Status.USED), 0),
            reserved=counts.get((code.id, Status.RESERVED), 0),
        )
        for code in codes
    ]


async def redemptions(session: AsyncSession, code_id: int) -> list[tuple[PromoRedemption, str]]:
    rows = await session.execute(
        select(PromoRedemption, Trainer.display_name)
        .join(Trainer, Trainer.id == PromoRedemption.trainer_id)
        .where(PromoRedemption.code_id == code_id)
        .order_by(PromoRedemption.created_at.desc())
    )
    return [(row, name) for row, name in rows.all()]
