"""Правило тренера о записи без блока: разрешать, с подтверждением, запрещать."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_bookings import ELEVEN, TEN, book, me_id, new_client, setup_trainer
from tests.test_offline_clients import trainer_books
from tests.test_packages import sell
from tests.test_schedule_api import Headers


async def set_mode(client: AsyncClient, headers: Headers, mode: str) -> None:
    response = await client.patch("/api/trainer/me", headers=headers, json={"one_off_mode": mode})
    assert response.status_code == 200, response.text
    assert response.json()["one_off_mode"] == mode


async def test_default_allows_booking_without_block(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers, trainer_id, service_id = await setup_trainer(client)
    assert (await client.get("/api/trainer/me", headers=headers)).json()["one_off_mode"] == "allow"
    client_headers = await new_client(client, session, trainer_id, 3003)
    trainers = (await client.get("/api/client/trainers", headers=client_headers)).json()
    assert trainers[0]["one_off_mode"] == "allow"
    status_code, body = await book(client, client_headers, trainer_id, service_id)
    assert (status_code, body["status"]) == (201, "confirmed")


async def test_forbid_needs_a_free_session_in_block(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers, trainer_id, service_id = await setup_trainer(client)
    await set_mode(client, headers, "forbid")
    client_headers = await new_client(client, session, trainer_id, 3003)

    status_code, body = await book(client, client_headers, trainer_id, service_id)
    assert status_code == 409
    assert "только по блоку" in str(body["detail"])

    # Блок на одно занятие: первая запись проходит, вторую уже не из чего списать
    await sell(client, headers, await me_id(client, client_headers), sessions_count=1)
    status_code, _ = await book(client, client_headers, trainer_id, service_id, TEN)
    assert status_code == 201
    status_code, _ = await book(client, client_headers, trainer_id, service_id, ELEVEN)
    assert status_code == 409

    # Тренера правило не ограничивает
    await trainer_books(client, headers, await me_id(client, client_headers), service_id, ELEVEN)


async def test_confirm_makes_booking_without_block_pending(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers, trainer_id, service_id = await setup_trainer(client)
    await set_mode(client, headers, "confirm")
    client_headers = await new_client(client, session, trainer_id, 3003)

    status_code, body = await book(client, client_headers, trainer_id, service_id, TEN)
    assert (status_code, body["status"]) == (201, "pending")

    await sell(client, headers, await me_id(client, client_headers))
    status_code, body = await book(client, client_headers, trainer_id, service_id, ELEVEN)
    assert (status_code, body["status"]) == (201, "confirmed")
