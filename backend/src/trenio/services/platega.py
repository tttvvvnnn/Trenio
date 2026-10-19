"""Клиент Platega: создать платёж по СБП и узнать его статус.

Так же, как в боте TVN VPN: POST /transaction/process и GET /transaction/{id},
авторизация заголовками X-MerchantId и X-Secret.
"""

from dataclasses import dataclass

import httpx

from trenio.config import get_settings

BASE_URL = "https://app.platega.io"
# Способ оплаты 2 — СБП по QR-коду
SBP = 2
# Конечные статусы транзакции; остальные (PENDING и т.п.) — ещё ждём
CONFIRMED = "CONFIRMED"
FAILED = frozenset({"CANCELED", "CHARGEBACKED", "NOT_FOUND"})


@dataclass(frozen=True, slots=True)
class CreatedPayment:
    transaction_id: str
    redirect_url: str


class PlategaError(Exception):
    pass


def _headers() -> dict[str, str]:
    settings = get_settings()
    return {
        "X-MerchantId": settings.platega_merchant_id,
        "X-Secret": settings.platega_api_key.get_secret_value(),
        "Content-Type": "application/json",
    }


async def create_payment(
    amount: int, order_id: str, description: str, return_url: str
) -> CreatedPayment:
    body = {
        "paymentMethod": SBP,
        "paymentDetails": {"amount": amount, "currency": "RUB"},
        "description": description,
        "payload": order_id,
        "return": return_url,
        "failedUrl": return_url,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{BASE_URL}/transaction/process", json=body, headers=_headers()
            )
            response.raise_for_status()
            data = response.json()
        return CreatedPayment(transaction_id=data["transactionId"], redirect_url=data["redirect"])
    except (httpx.HTTPError, KeyError, ValueError) as error:
        raise PlategaError(str(error)) from error


async def get_status(transaction_id: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{BASE_URL}/transaction/{transaction_id}", headers=_headers()
            )
            if response.status_code == 404:
                return "NOT_FOUND"
            response.raise_for_status()
            status: str = response.json().get("status", "")
            return status
    except (httpx.HTTPError, ValueError) as error:
        raise PlategaError(str(error)) from error
