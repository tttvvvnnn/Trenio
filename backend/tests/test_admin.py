"""Админ-панель: общая статистика, тренеры, приглашения."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_bookings import new_client, setup_trainer
from tests.test_finance import booking_at
from tests.test_packages import client_id_of, mark, sell
from tests.test_schedule_api import Headers, auth, second_trainer
from trenio.services.admin_stats import ADMIN_TIMEZONE


async def get(client: AsyncClient, headers: Headers, path: str) -> Any:
    response = await client.get(f"/api/admin/{path}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def test_overview_and_trainers(client: AsyncClient, session: AsyncSession) -> None:
    headers, trainer_id, service_id = await setup_trainer(client, price=2500)
    response = await client.patch(
        "/api/trainer/me", headers=headers, json={"display_name": "Админ"}
    )
    assert response.status_code == 200
    other = await second_trainer(client, session)
    anna = await client_id_of(client, await new_client(client, session, trainer_id, 501))
    await new_client(client, session, trainer_id, 502)

    # День по Москве: по нему админка делит деньги на месяцы
    today = datetime.now(ADMIN_TIMEZONE).date().isoformat()
    package = await sell(client, headers, anna, purchased_on=today)
    response = await client.post(
        f"/api/trainer/packages/{package['id']}/payments",
        headers=headers,
        json={"amount": 7000, "paid_on": today, "comment": None},
    )
    assert response.status_code == 201
    yesterday = datetime.now(UTC).replace(microsecond=0) - timedelta(days=1)
    held = await booking_at(session, trainer_id, anna, service_id, yesterday)
    assert (await mark(client, headers, held, "attended"))[0] == 200

    overview = await get(client, headers, "overview")
    # Админ, второй тренер и два клиента, все заходили в Mini App
    assert overview["users"] == 4
    assert overview["users_seen_week"] == 4
    assert overview["trainers"] == 2
    assert overview["trainers_active"] == 2
    assert overview["clients"] == 2
    assert overview["clients_new_week"] == 2
    assert overview["bookings_week"] == 1
    assert overview["attended_week"] == 1
    assert overview["funnel"] == {
        "trainers": 2,
        "onboarded": 1,
        "set_up": 1,
        "with_clients": 1,
        "with_bookings": 1,
    }
    assert len(overview["weeks"]) == 8
    assert overview["weeks"][-1]["new_clients"] == 2
    # Занятие из блока списалось, поэтому денег — только оплата блока, в целом по платформе
    money = overview["money"]
    assert money["packages_sold"] == 1
    assert money["packages_amount"] == 20000
    assert money["received"] == 7000

    trainers = await get(client, headers, "trainers")
    assert [(t["id"], t["state"], t["clients"], t["bookings_month"]) for t in trainers] == [
        (trainer_id, "active", 2, 1),
        (trainers[1]["id"], "not_set_up", 0, 0),
    ]
    assert trainers[0]["is_admin"] is True
    # Денег отдельных тренеров в админке нет
    assert not any("received" in key or "price" in key for key in trainers[0])

    # Админа отключить нельзя, другого тренера — можно
    response = await client.post(
        f"/api/admin/trainers/{trainer_id}/active", headers=headers, json={"active": False}
    )
    assert response.status_code == 409
    response = await client.post(
        f"/api/admin/trainers/{trainers[1]['id']}/active", headers=headers, json={"active": False}
    )
    assert response.status_code == 204
    assert (await client.get("/api/trainer/me", headers=other)).status_code == 403


async def test_invites(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from trenio.api.routes import admin as routes

    async def username() -> str:
        return "trenio_test_bot"

    monkeypatch.setattr(routes, "get_bot_username", username)
    headers = await auth(client)
    response = await client.post("/api/admin/invites", headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()["url"].startswith("https://t.me/trenio_test_bot?start=tr_")
    assert len(await get(client, headers, "invites")) == 1
    assert (await get(client, headers, "overview"))["invites_open"] == 1


async def test_admin_only(client: AsyncClient, session: AsyncSession) -> None:
    other = await second_trainer(client, session)
    for path in ("overview", "trainers", "invites"):
        assert (await client.get(f"/api/admin/{path}", headers=other)).status_code == 403
