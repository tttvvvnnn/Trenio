"""Промокоды: дни Pro сразу, скидка на следующую оплату, лимиты и админка."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_admin import get
from tests.test_billing import FakePlatega, fake, invited_trainer, pay  # noqa: F401
from tests.test_bookings import setup_trainer, trainer_row
from tests.test_schedule_api import Headers, second_trainer
from trenio.db.models import PromoRedemption


async def _create(client: AsyncClient, admin: Headers, **fields: object) -> dict[str, object]:
    response = await client.post("/api/admin/promo-codes", headers=admin, json=fields)
    assert response.status_code == 201, response.text
    data: dict[str, object] = response.json()
    return data


async def _redeem(
    client: AsyncClient, headers: Headers, code: str
) -> tuple[int, dict[str, object]]:
    response = await client.post("/api/trainer/promo-code", headers=headers, json={"code": code})
    return response.status_code, response.json()


async def test_days_code(client: AsyncClient, session: AsyncSession) -> None:
    admin, _, _ = await setup_trainer(client)
    other = await second_trainer(client, session)
    await _create(client, admin, code="month-free", kind="days", value=30, max_uses=1)
    trainer = await trainer_row(session, 2)
    trial_end = trainer.trial_until
    assert trial_end is not None

    status, body = await _redeem(client, other, " Month-Free ")
    assert status == 200, body
    assert body["state"] == "pro"
    trainer = await trainer_row(session, 2)
    assert trainer.pro_until is not None
    assert abs(trainer.pro_until - (trial_end + timedelta(days=30))) < timedelta(seconds=5)

    status, body = await _redeem(client, other, "MONTH-FREE")
    assert (status, body["detail"]) == (422, "Вы уже вводили этот промокод")
    status, body = await _redeem(client, other, "NOPE")
    assert (status, body["detail"]) == (422, "Такого промокода нет")

    codes = await get(client, admin, "promo-codes")
    assert [(c["code"], c["used"]) for c in codes] == [("MONTH-FREE", 1)]
    rows = await get(client, admin, f"promo-codes/{codes[0]['id']}/redemptions")
    assert [r["status"] for r in rows] == ["used"]


async def test_limits_and_disable(client: AsyncClient, session: AsyncSession) -> None:
    admin, _, _ = await setup_trainer(client)
    other = await second_trainer(client, session)
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    await _create(client, admin, code="OLD", kind="days", value=5, expires_at=past)
    status, body = await _redeem(client, other, "old")
    assert (status, body["detail"]) == (422, "Срок промокода закончился")

    code = await _create(client, admin, code="OFF", kind="days", value=5)
    response = await client.post(
        f"/api/admin/promo-codes/{code['id']}/active", headers=admin, json={"active": False}
    )
    assert response.status_code == 204
    assert (await _redeem(client, other, "OFF"))[0] == 422

    response = await client.post(
        "/api/admin/promo-codes", headers=admin, json={"code": "off", "kind": "days", "value": 1}
    )
    assert response.status_code == 409
    response = await client.post(
        "/api/admin/promo-codes",
        headers=admin,
        json={"code": "TOO", "kind": "percent", "value": 100},
    )
    assert response.status_code == 422


async def test_discount_applies_to_next_payment(
    client: AsyncClient,
    session: AsyncSession,
    fake: FakePlatega,  # noqa: F811
) -> None:
    admin, _, _ = await setup_trainer(client)
    headers, _, boris = await invited_trainer(client, session)
    await _create(client, admin, code="HALF", kind="percent", value=50)

    status, body = await _redeem(client, headers, "half")
    assert status == 200, body
    assert body["discount"] == {"code": "HALF", "kind": "percent", "value": 50}
    plans = body["plans"]
    assert isinstance(plans, list) and [p["price"] for p in plans] == [175]

    # Оплата сорвалась: скидка остаётся за тренером
    payment = await pay(client, headers)
    assert payment["amount"] == 175 and fake.created[-1][0] == 175
    fake.statuses["tx-1"] = "CANCELED"
    await client.get(f"/api/trainer/subscription/payments/{payment['id']}", headers=headers)
    sub = (await client.get("/api/trainer/subscription", headers=headers)).json()
    assert sub["discount"] is not None

    payment = await pay(client, headers)
    fake.statuses["tx-2"] = "CONFIRMED"
    await client.get(f"/api/trainer/subscription/payments/{payment['id']}", headers=headers)
    sub = (await client.get("/api/trainer/subscription", headers=headers)).json()
    assert sub["discount"] is None and sub["plans"][0]["price"] == 349

    row = await session.scalar(
        select(PromoRedemption).where(PromoRedemption.trainer_id == boris.id)
    )
    assert row is not None and row.status == "used" and row.payment_id == payment["id"]
