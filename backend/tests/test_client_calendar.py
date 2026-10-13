"""Записи клиента за период: календарь клиента показывает и прошедшие."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_bookings import new_client, setup_trainer
from tests.test_packages import client_id_of, past_booking


async def test_client_bookings_for_period(client: AsyncClient, session: AsyncSession) -> None:
    headers, trainer_id, service_id = await setup_trainer(client)
    client_headers = await new_client(client, session, trainer_id, 3003)
    client_id = await client_id_of(client, client_headers)
    old = await past_booking(session, trainer_id, client_id, service_id, 3)
    ancient = await past_booking(session, trainer_id, client_id, service_id, 90)
    upcoming = await past_booking(session, trainer_id, client_id, service_id, -2)
    assert (
        await client.post(
            f"/api/trainer/bookings/{old}/attendance",
            headers=headers,
            json={"attendance": "attended"},
        )
    ).status_code == 200

    # Без периода — только предстоящие, как раньше
    response = await client.get("/api/client/bookings", headers=client_headers)
    assert [b["id"] for b in response.json()] == [upcoming]

    start = (datetime.now(UTC) - timedelta(days=10)).date().isoformat()
    response = await client.get(
        "/api/client/bookings",
        headers=client_headers,
        params={"from": start, "days": 20, "trainer_id": trainer_id},
    )
    assert response.status_code == 200, response.text
    found = response.json()
    assert [b["id"] for b in found] == [old, upcoming]
    assert found[0]["attendance"] == "attended"
    assert ancient not in [b["id"] for b in found]

    response = await client.get(
        "/api/client/bookings",
        headers=client_headers,
        params={"from": start, "days": 20, "trainer_id": trainer_id + 100},
    )
    assert response.json() == []
