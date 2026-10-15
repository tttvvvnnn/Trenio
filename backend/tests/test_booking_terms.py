"""Свои условия одного занятия: длительность, цена разового, не списывать из блока."""

from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_bookings import ELEVEN, TEN, me_id, new_client, setup_trainer
from tests.test_packages import mark, past_booking, sell
from tests.test_schedule_api import Headers, create_service
from trenio.db.models import Notification


async def trainer_books(
    client: AsyncClient, headers: Headers, **body: object
) -> tuple[int, dict[str, Any]]:
    response = await client.post("/api/trainer/bookings", headers=headers, json=body)
    return response.status_code, response.json()


async def set_terms(
    client: AsyncClient, headers: Headers, booking_id: int, **body: object
) -> tuple[int, dict[str, Any]]:
    response = await client.patch(
        f"/api/trainer/bookings/{booking_id}/terms", headers=headers, json=body
    )
    return response.status_code, response.json()


async def test_trainer_sets_terms_when_booking(client: AsyncClient, session: AsyncSession) -> None:
    headers, trainer_id, service_id = await setup_trainer(client, price=2500)
    client_headers = await new_client(client, session, trainer_id, 3003)
    client_id = await me_id(client, client_headers)

    code, booking = await trainer_books(
        client,
        headers,
        client_id=client_id,
        service_id=service_id,
        starts_at=TEN,
        duration_min=90,
        price=3000,
        no_package=True,
    )
    assert code == 201, booking
    assert booking["ends_at"] == "2030-01-07T08:30:00Z"
    assert (booking["price"], booking["no_package"], booking["one_off"]) == (3000, True, True)
    # Клиент видит время, но не цену
    mine = (await client.get("/api/client/bookings", headers=client_headers)).json()
    assert [(b["ends_at"], b["price"]) for b in mine] == [("2030-01-07T08:30:00Z", None)]

    # Цена записи — копия цены услуги: правка услуги прошлые записи не меняет
    code, plain = await trainer_books(
        client,
        headers,
        client_id=client_id,
        service_id=service_id,
        starts_at="2030-01-14T07:00:00Z",
    )
    assert code == 201 and plain["price"] == 2500
    await client.patch(f"/api/trainer/services/{service_id}", headers=headers, json={"price": 4000})
    again = (await client.get(f"/api/trainer/bookings/{plain['id']}", headers=headers)).json()
    assert again["price"] == 2500


async def test_group_duration_is_shared(client: AsyncClient, session: AsyncSession) -> None:
    headers, trainer_id, _ = await setup_trainer(client)
    group = await create_service(client, headers, name="Группа", capacity=5)
    client_id = await me_id(client, await new_client(client, session, trainer_id, 3003))
    code, body = await trainer_books(
        client, headers, client_id=client_id, service_id=group, starts_at=TEN, duration_min=90
    )
    assert code == 409, body
    code, booking = await trainer_books(
        client, headers, client_id=client_id, service_id=group, starts_at=TEN
    )
    assert code == 201
    code, _ = await set_terms(client, headers, booking["id"], duration_min=90)
    assert code == 409


async def test_change_duration(client: AsyncClient, session: AsyncSession) -> None:
    headers, trainer_id, service_id = await setup_trainer(client)
    client_headers = await new_client(client, session, trainer_id, 3003)
    client_id = await me_id(client, client_headers)
    _, first = await trainer_books(
        client, headers, client_id=client_id, service_id=service_id, starts_at=TEN
    )
    other = await me_id(client, await new_client(client, session, trainer_id, 4004))
    await trainer_books(client, headers, client_id=other, service_id=service_id, starts_at=ELEVEN)

    # До 11:00 занято другим клиентом: 90 минут не влезают, 45 — пожалуйста
    code, body = await set_terms(client, headers, first["id"], duration_min=90)
    assert code == 409, body
    code, body = await set_terms(client, headers, first["id"], duration_min=45)
    assert code == 200, body
    assert body["ends_at"] == "2030-01-07T07:45:00Z"
    prompt = await session.scalar(
        select(Notification.send_at).where(
            Notification.booking_id == first["id"], Notification.kind == "attendance_prompt"
        )
    )
    assert prompt == datetime(2030, 1, 7, 7, 45, tzinfo=UTC)

    # Перенос сохраняет свою длительность
    response = await client.post(
        f"/api/trainer/bookings/{first['id']}/reschedule",
        headers=headers,
        json={"starts_at": "2030-01-14T07:00:00Z"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["ends_at"] == "2030-01-14T07:45:00Z"


async def test_no_package_moves_session_out_of_block(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers, trainer_id, service_id = await setup_trainer(client, price=2000)
    client_id = await me_id(client, await new_client(client, session, trainer_id, 3003))
    package = await sell(client, headers, client_id)
    booking_id = await past_booking(session, trainer_id, client_id, service_id, days_ago=0)
    code, marked = await mark(client, headers, booking_id, "attended")
    assert code == 200 and marked["charge"]["package_id"] == package["id"]

    code, body = await set_terms(client, headers, booking_id, no_package=True, price=1500)
    assert code == 200, body
    assert (body["charge"], body["one_off"], body["price"]) == (None, True, 1500)
    finance = (await client.get("/api/trainer/finance/summary", headers=headers)).json()
    assert finance["from_one_off"] == 1500

    code, body = await set_terms(client, headers, booking_id, no_package=False)
    assert code == 200, body
    assert body["charge"]["package_id"] == package["id"] and not body["one_off"]

    # Прошедшему занятию длительность уже не поменять
    code, _ = await set_terms(client, headers, booking_id, duration_min=90)
    assert code == 409
    # Будущая запись с «не из блока» в прогноз блока не попадает
    _, future = await trainer_books(
        client,
        headers,
        client_id=client_id,
        service_id=service_id,
        starts_at=(datetime.now(UTC) + timedelta(days=30)).replace(microsecond=0).isoformat(),
        no_package=True,
    )
    assert future["planned"] is None and future["one_off"]
    # Тренер сам так решил: тревогой «блок закончился» не подсвечиваем
    assert not future["out_of_block"]
    clients = (await client.get("/api/trainer/clients", headers=headers)).json()
    assert clients[0]["upcoming_one_off"] == 0
