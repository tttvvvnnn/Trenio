"""Тарифы из админки: цена, пробный период и лимит бесплатного тарифа."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_admin import get
from tests.test_bookings import setup_trainer
from tests.test_schedule_api import second_trainer
from trenio.db.models import AdminAuditEntry, Trainer
from trenio.services import subscription


async def test_defaults_and_update(client: AsyncClient, session: AsyncSession) -> None:
    headers, _, _ = await setup_trainer(client)
    assert await get(client, headers, "plans") == {
        "price_month": 349,
        "trial_days": 30,
        "free_client_limit": 3,
    }
    body = {"price_month": 399, "trial_days": 14, "free_client_limit": 5}
    response = await client.put("/api/admin/plans", headers=headers, json=body)
    assert response.status_code == 200, response.text
    assert await get(client, headers, "plans") == body
    response = await client.put(
        "/api/admin/plans", headers=headers, json={**body, "price_month": 0}
    )
    assert response.status_code == 422

    entry = await session.scalar(
        select(AdminAuditEntry).where(AdminAuditEntry.action == "plans.updated")
    )
    assert entry is not None and entry.payload["before"]["free_client_limit"] == 3

    # Новый тренер получает новый пробный период, цена и лимит видны в подписке и документах
    other = await second_trainer(client, session)
    sub = (await client.get("/api/trainer/subscription", headers=other)).json()
    assert sub["free_client_limit"] == 5
    assert [p["price"] for p in sub["plans"]] == [399]
    trainer = await session.scalar(select(Trainer).where(Trainer.id == 2))
    assert trainer is not None and trainer.trial_until is not None
    left = trainer.trial_until - datetime.now(UTC)
    assert timedelta(days=13) < left <= timedelta(days=14)
    terms = (await client.get("/api/legal/terms")).json()["text"]
    assert "399" in terms


async def test_free_limit_applies(client: AsyncClient, session: AsyncSession) -> None:
    headers, _, _ = await setup_trainer(client)
    other = await second_trainer(client, session)
    # Пробный период кончился: второй тренер на бесплатном тарифе
    await session.execute(
        update(Trainer).where(Trainer.id == 2).values(trial_until=datetime.now(UTC))
    )
    await session.commit()

    async def add(name: str) -> int:
        response = await client.post(
            "/api/trainer/clients", headers=other, json={"first_name": name}
        )
        return response.status_code

    assert [await add(f"Клиент {i}") for i in range(4)] == [201, 201, 201, 402]
    await subscription.save_terms(session, subscription.Terms(free_client_limit=5))
    await session.commit()
    assert await add("Четвёртый") == 201
