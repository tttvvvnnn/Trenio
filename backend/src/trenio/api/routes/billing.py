import hmac
import logging
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from trenio.api.deps import CurrentTrainer, SessionDep, SettingsDep
from trenio.bot.setup import get_bot_username
from trenio.db.models import SubscriptionPayment
from trenio.services import billing

logger = logging.getLogger(__name__)

router = APIRouter(tags=["billing"])


class PayIn(BaseModel):
    plan: Literal["month"]


class PaymentOut(BaseModel):
    id: int
    # pending, paid или canceled
    status: str
    plan: str
    price: int
    amount: int
    balance_used: int
    # Страница оплаты по СБП; None — платить деньгами не нужно
    redirect_url: str | None

    @classmethod
    def of(cls, payment: SubscriptionPayment) -> "PaymentOut":
        return cls(
            id=payment.id,
            status=payment.status,
            plan=payment.plan,
            price=payment.price,
            amount=payment.amount,
            balance_used=payment.balance_used,
            redirect_url=payment.redirect_url if payment.status == "pending" else None,
        )


@router.post("/trainer/subscription/pay", status_code=status.HTTP_201_CREATED)
async def pay(body: PayIn, trainer: CurrentTrainer, session: SessionDep) -> PaymentOut:
    """Оплата Pro: сначала баланс, остальное по СБП через Platega."""
    return_url = f"https://t.me/{await get_bot_username()}"
    try:
        payment = await billing.start_payment(
            session, trainer, body.plan, return_url, datetime.now(UTC)
        )
    except billing.PaymentUnavailable:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Оплата сейчас недоступна. Попробуйте чуть позже.",
        ) from None
    return PaymentOut.of(payment)


@router.get("/trainer/subscription/payments/{payment_id}")
async def get_payment(payment_id: int, trainer: CurrentTrainer, session: SessionDep) -> PaymentOut:
    """Статус оплаты; ожидающую заодно проверяем в Platega."""
    payment = await billing.get_payment(session, trainer, payment_id)
    if payment is None:
        raise HTTPException(404, "Оплата не найдена")
    await billing.refresh(session, payment, datetime.now(UTC))
    return PaymentOut.of(payment)


@router.post("/platega/callback", include_in_schema=False)
async def platega_callback(
    request: Request, session: SessionDep, settings: SettingsDep
) -> Response:
    """Platega сообщает о смене статуса. Телу не верим: статус перепроверяем через API."""
    merchant = request.headers.get("X-MerchantId", "")
    secret = request.headers.get("X-Secret", "")
    if not settings.payments_enabled or not (
        hmac.compare_digest(merchant, settings.platega_merchant_id)
        and hmac.compare_digest(secret, settings.platega_api_key.get_secret_value())
    ):
        return Response(status_code=status.HTTP_401_UNAUTHORIZED)
    try:
        data = await request.json()
        transaction_id = str(data["id"])
    except (ValueError, KeyError, TypeError):
        return Response(status_code=status.HTTP_400_BAD_REQUEST)
    await billing.refresh_by_transaction(session, transaction_id, datetime.now(UTC))
    return Response(status_code=status.HTTP_200_OK)
