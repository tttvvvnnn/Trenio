"""Заметки к занятиям и замеры клиента."""

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_bookings import book, me_id, new_client, setup_trainer
from tests.test_offline_clients import bot_username
from trenio.db.models import Booking, ClientMeasurement

__all__ = ["bot_username"]


async def test_note_hidden_from_client_when_private(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers, trainer_id, service_id = await setup_trainer(client)
    client_headers = await new_client(client, session, trainer_id, 3003)
    status_code, booked = await book(client, client_headers, trainer_id, service_id)
    assert status_code == 201
    url = f"/api/trainer/bookings/{booked['id']}/note"

    saved = await client.put(url, headers=headers, json={"note": "  присед 3×10, 60 кг  "})
    assert (saved.json()["note"], saved.json()["note_private"]) == ("присед 3×10, 60 кг", False)
    mine = (await client.get("/api/client/bookings", headers=client_headers)).json()
    assert mine[0]["note"] == "присед 3×10, 60 кг"

    await client.put(url, headers=headers, json={"note": "жаловался на колено", "private": True})
    mine = (await client.get("/api/client/bookings", headers=client_headers)).json()
    assert (mine[0]["note"], mine[0]["note_private"]) == (None, False)
    trainer_view = (
        await client.get(f"/api/trainer/bookings/{booked['id']}", headers=headers)
    ).json()
    assert (trainer_view["note"], trainer_view["note_private"]) == ("жаловался на колено", True)

    cleared = await client.put(url, headers=headers, json={"note": " ", "private": True})
    assert (cleared.json()["note"], cleared.json()["note_private"]) == (None, False)


async def test_measurements_series_and_client_view(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers, trainer_id, _ = await setup_trainer(client)
    client_headers = await new_client(client, session, trainer_id, 3003)
    client_id = await me_id(client, client_headers)
    url = f"/api/trainer/clients/{client_id}/measurements"

    for day, value in (("2030-01-01", 80.5), ("2030-02-01", 78)):
        response = await client.post(
            url, headers=headers, json={"day": day, "kind": "weight", "value": value}
        )
        assert response.status_code == 200, response.text
    # Тот же день — замена, а не второй замер
    await client.post(
        url, headers=headers, json={"day": "2030-02-01", "kind": "weight", "value": 77.4}
    )
    custom = {"day": "2030-02-01", "kind": "custom", "label": "Планка", "unit": "сек", "value": 90}
    series = (await client.post(url, headers=headers, json=custom)).json()
    assert [item["key"] for item in series] == ["weight", "custom:планка"]
    assert [p["value"] for p in series[0]["points"]] == [80.5, 77.4]
    assert (series[0]["label"], series[0]["unit"]) == ("Вес", "кг")
    assert (series[1]["label"], series[1]["unit"]) == ("Планка", "сек")

    no_label = await client.post(url, headers=headers, json={**custom, "label": " "})
    assert no_label.status_code == 422
    unknown = await client.post(url, headers=headers, json={**custom, "kind": "iq"})
    assert unknown.status_code == 422

    mine = (await client.get("/api/client/progress", headers=client_headers)).json()
    assert mine[0]["trainer_id"] == trainer_id
    assert [item["key"] for item in mine[0]["series"]] == ["weight", "custom:планка"]
    # Клиент только смотрит
    denied = await client.post(url, headers=client_headers, json=custom)
    assert denied.status_code == 403

    point = series[1]["points"][0]["id"]
    left = await client.delete(f"{url}/{point}", headers=headers)
    assert [item["key"] for item in left.json()] == ["weight"]
    assert (await client.delete(f"{url}/{point}", headers=headers)).status_code == 404


async def test_account_deletion_forgets_notes_and_measurements(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers, trainer_id, service_id = await setup_trainer(client)
    client_headers = await new_client(client, session, trainer_id, 3003)
    client_id = await me_id(client, client_headers)
    _, booked = await book(client, client_headers, trainer_id, service_id)
    await client.put(
        f"/api/trainer/bookings/{booked['id']}/note", headers=headers, json={"note": "жим"}
    )
    await client.post(
        f"/api/trainer/clients/{client_id}/measurements",
        headers=headers,
        json={"day": "2030-01-01", "kind": "waist", "value": 70},
    )

    assert (await client.delete("/api/me", headers=client_headers)).status_code == 204
    session.expire_all()
    assert await session.scalar(select(func.count()).select_from(ClientMeasurement)) == 0
    booking = await session.get(Booking, booked["id"])
    assert booking is not None and booking.trainer_note is None
