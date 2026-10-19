"""Оплата Pro через Platega, баланс и 20% пригласившему."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import make_init_data
from tests.test_api import login
from tests.test_bookings import trainer_row
from tests.test_referrals import make_trainer
from tests.test_schedule_api import Headers, auth
from tests.test_trainers import make_user
from trenio.db.models import BalanceEntry, Notification, Trainer
from trenio.delivery.texts import render
from trenio.services import billing, platega
from trenio.services.trainers import accept_referral

MERCHANT = "merchant-1"
SECRET = "secret-1"


class FakePlatega:
    def __init__(self) -> None:
        self.statuses: dict[str, str] = {}
        self.created: list[tuple[int, str]] = []
        self.fail = False

    async def create_payment(
        self, amount: int, order_id: str, description: str, return_url: str
    ) -> platega.CreatedPayment:
        if self.fail:
            raise platega.PlategaError("down")
        transaction_id = f"tx-{len(self.created) + 1}"
        self.created.append((amount, order_id))
        self.statuses[transaction_id] = "PENDING"
        return platega.CreatedPayment(transaction_id, f"https://pay.example/{transaction_id}")

    async def get_status(self, transaction_id: str) -> str:
        return self.statuses.get(transaction_id, "NOT_FOUND")


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakePlatega]:
    from trenio.api.routes import billing as routes
    from trenio.api.routes import trainer as trainer_routes
    from trenio.config import get_settings

    fake = FakePlatega()
    monkeypatch.setattr(platega, "create_payment", fake.create_payment)
    monkeypatch.setattr(platega, "get_status", fake.get_status)
    monkeypatch.setenv("PLATEGA_MERCHANT_ID", MERCHANT)
    monkeypatch.setenv("PLATEGA_API_KEY", SECRET)
    get_settings.cache_clear()

    async def username() -> str:
        return "trenio_test_bot"

    monkeypatch.setattr(routes, "get_bot_username", username)
    monkeypatch.setattr(trainer_routes, "get_bot_username", username)
    yield fake
    get_settings.cache_clear()


async def invited_trainer(
    client: AsyncClient, session: AsyncSession
) -> tuple[Headers, Trainer, Trainer]:
    """Анна пригласила Бориса; возвращает вход Бориса, Анну и Бориса."""
    anna = await make_trainer(session, 7, "Анна")
    boris_user = await make_user(session, 8, "Борис")
    boris = await accept_referral(session, boris_user, anna.referral_code)
    token = await login(client, make_init_data(user_id=8, first_name="Борис"))
    return {"Authorization": f"Bearer {token}"}, anna, boris


async def pay(client: AsyncClient, headers: Headers, plan: str = "month") -> dict[str, object]:
    response = await client.post(
        "/api/trainer/subscription/pay", headers=headers, json={"plan": plan}
    )
    assert response.status_code == 201, response.text
    data: dict[str, object] = response.json()
    return data


async def test_payment_extends_pro_and_rewards_inviter(
    client: AsyncClient, session: AsyncSession, fake: FakePlatega
) -> None:
    headers, anna, boris = await invited_trainer(client, session)
    trial_end = (await trainer_row(session, boris.id)).trial_until
    assert trial_end is not None

    payment = await pay(client, headers)
    assert payment["status"] == "pending"
    assert payment["amount"] == 349
    assert payment["redirect_url"] == "https://pay.example/tx-1"
    assert fake.created == [(349, f"trenio_{payment['id']}")]

    # Пока Platega не подтвердила, ничего не меняется
    path = f"/api/trainer/subscription/payments/{payment['id']}"
    assert (await client.get(path, headers=headers)).json()["status"] == "pending"

    # Подтверждение приходит callback-ом; статус перепроверяется через API
    fake.statuses["tx-1"] = "CONFIRMED"
    response = await client.post(
        "/api/platega/callback",
        headers={"X-MerchantId": MERCHANT, "X-Secret": SECRET},
        json={"id": "tx-1", "status": "CONFIRMED"},
    )
    assert response.status_code == 200
    assert (await client.get(path, headers=headers)).json()["status"] == "paid"

    boris = await trainer_row(session, boris.id)
    assert boris.pro_until is not None
    # Оплаченные дни идут после пробного периода
    assert abs(boris.pro_until - (trial_end + timedelta(days=30))) < timedelta(seconds=5)

    anna = await trainer_row(session, anna.id)
    assert anna.balance == 69  # 20% от 349 с округлением вниз
    referrals = await client.get("/api/trainer/referrals", headers=await anna_headers(client))
    data = referrals.json()
    assert data["balance"] == 69 and data["earned"] == 69 and data["percent"] == 20
    assert data["trainers"][0]["paid"] is True

    # Повторный callback ничего не начисляет второй раз
    await client.post(
        "/api/platega/callback",
        headers={"X-MerchantId": MERCHANT, "X-Secret": SECRET},
        json={"id": "tx-1"},
    )
    assert (await trainer_row(session, anna.id)).balance == 69

    rows = (
        await session.scalars(
            select(Notification).where(
                Notification.kind.in_(["subscription_paid", "referral_bonus"])
            )
        )
    ).all()
    texts = [m.text for row in rows if (m := await render(session, row, datetime.now(UTC)))]
    assert any(text.startswith("✅ Pro оплачен") for text in texts)
    assert any("Борис оплатил(а) Pro, вам начислено 69" in text for text in texts)


async def anna_headers(client: AsyncClient) -> Headers:
    token = await login(client, make_init_data(user_id=7, first_name="Анна"))
    return {"Authorization": f"Bearer {token}"}


async def test_balance_is_spent_and_refunded(
    client: AsyncClient, session: AsyncSession, fake: FakePlatega
) -> None:
    headers, _, boris = await invited_trainer(client, session)
    trainer = await trainer_row(session, boris.id)
    trainer.balance = 320
    await session.commit()

    # К оплате остаётся не меньше 50 ₽: столько минимум принимает Platega
    sub = (await client.get("/api/trainer/subscription", headers=headers)).json()
    month = sub["plans"][0]
    assert (month["balance_used"], month["amount"]) == (299, 50)

    payment = await pay(client, headers)
    assert (payment["balance_used"], payment["amount"]) == (299, 50)
    assert (await trainer_row(session, boris.id)).balance == 21

    # Оплата не прошла — баланс вернулся
    fake.statuses["tx-1"] = "CANCELED"
    path = f"/api/trainer/subscription/payments/{payment['id']}"
    assert (await client.get(path, headers=headers)).json()["status"] == "canceled"
    assert (await trainer_row(session, boris.id)).balance == 320
    kinds = (await session.scalars(select(BalanceEntry.kind).order_by(BalanceEntry.id))).all()
    assert kinds == ["payment", "refund"]


async def test_balance_covers_whole_plan(
    client: AsyncClient, session: AsyncSession, fake: FakePlatega
) -> None:
    headers, anna, boris = await invited_trainer(client, session)
    trainer = await trainer_row(session, boris.id)
    trainer.balance = 400
    await session.commit()
    payment = await pay(client, headers)
    assert payment["status"] == "paid"
    assert (payment["amount"], payment["balance_used"], payment["redirect_url"]) == (0, 349, None)
    assert fake.created == []
    assert (await trainer_row(session, boris.id)).balance == 51
    # С оплаты балансом пригласившему ничего не начисляется
    assert (await trainer_row(session, anna.id)).balance == 0


async def test_payment_errors(
    client: AsyncClient, session: AsyncSession, fake: FakePlatega
) -> None:
    headers, _, _ = await invited_trainer(client, session)
    fake.fail = True
    response = await client.post(
        "/api/trainer/subscription/pay", headers=headers, json={"plan": "year"}
    )
    assert response.status_code == 503

    # Чужой callback отбрасывается
    response = await client.post(
        "/api/platega/callback",
        headers={"X-MerchantId": MERCHANT, "X-Secret": "wrong"},
        json={"id": "tx-1"},
    )
    assert response.status_code == 401


async def test_sweep_pending(client: AsyncClient, session: AsyncSession, fake: FakePlatega) -> None:
    headers, _, boris = await invited_trainer(client, session)
    first = await pay(client, headers)
    second = await pay(client, headers, "year")
    fake.statuses["tx-1"] = "CONFIRMED"
    now = datetime.now(UTC)
    await billing.sweep_pending(session, now)
    trainer = await trainer_row(session, boris.id)
    assert trainer.pro_until is not None
    # Не подтверждённая за сутки оплата отменяется
    await billing.sweep_pending(session, now + timedelta(days=2))
    for payment_id, status in ((first["id"], "paid"), (second["id"], "canceled")):
        path = f"/api/trainer/subscription/payments/{payment_id}"
        assert (await client.get(path, headers=headers)).json()["status"] == status


def test_split_price() -> None:
    assert billing.split_price(349, 0) == (0, 349)
    assert billing.split_price(349, 100) == (100, 249)
    assert billing.split_price(349, 349) == (349, 0)
    assert billing.split_price(349, 320) == (299, 50)
    assert billing.split_price(2990, 69) == (69, 2921)


async def test_payments_disabled(client: AsyncClient, session: AsyncSession) -> None:
    headers = await auth(client)
    sub = (await client.get("/api/trainer/subscription", headers=headers)).json()
    assert sub["payments_enabled"] is False
