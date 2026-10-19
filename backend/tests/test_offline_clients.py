"""Клиенты без Telegram: тренер заводит их сам, потом клиент привязывает свой Telegram."""

from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import ADMIN_TELEGRAM_ID
from tests.test_bookings import ELEVEN, TEN, me_id, new_client, setup_trainer, trainer_row
from tests.test_notifications import FakeChannel, dispatch
from tests.test_packages import sell
from tests.test_schedule_api import Headers, create_service
from tests.test_trainers import make_user
from trenio.db.models import Booking, Notification, Package, TrainerClient, User
from trenio.services.clients import LinkError, LinkRejected, claim


@pytest.fixture(autouse=True)
def bot_username(monkeypatch: pytest.MonkeyPatch) -> None:
    from trenio.api.routes import bookings as routes

    async def username() -> str:
        return "trenio_test_bot"

    monkeypatch.setattr(routes, "get_bot_username", username)


async def add_client(client: AsyncClient, headers: Headers, **fields: object) -> dict[str, Any]:
    body = {"first_name": "Мария", "last_name": "Офлайн", **fields}
    response = await client.post("/api/trainer/clients", headers=headers, json=body)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


async def trainer_books(
    client: AsyncClient, headers: Headers, client_id: object, service_id: int, starts_at: str = TEN
) -> int:
    body = {"client_id": client_id, "service_id": service_id, "starts_at": starts_at}
    response = await client.post("/api/trainer/bookings", headers=headers, json=body)
    assert response.status_code == 201, response.text
    booking_id: int = response.json()["id"]
    return booking_id


async def claim_code(client: AsyncClient, headers: Headers, client_id: object) -> str:
    response = await client.post(f"/api/trainer/clients/{client_id}/claim-link", headers=headers)
    assert response.status_code == 200, response.text
    url: str = response.json()["url"]
    assert url.startswith("https://t.me/trenio_test_bot?start=u_")
    return url.removeprefix("https://t.me/trenio_test_bot?start=u_")


async def test_trainer_adds_and_books_offline_client(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers, _, service_id = await setup_trainer(client)
    created = await add_client(client, headers, notes="  без телефона  ")
    assert created["offline"] is True
    assert (created["first_name"], created["last_name"]) == ("Мария", "Офлайн")

    clients = (await client.get("/api/trainer/clients", headers=headers)).json()
    assert [(c["id"], c["offline"]) for c in clients] == [(created["id"], True)]
    card = (await client.get(f"/api/trainer/clients/{created['id']}", headers=headers)).json()
    assert card["notes"] == "без телефона"

    renamed = await client.patch(
        f"/api/trainer/clients/{created['id']}",
        headers=headers,
        json={"first_name": "Мария", "last_name": None},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["last_name"] is None

    await trainer_books(client, headers, created["id"], service_id)
    # Писать клиенту без Telegram некуда: сообщения пропускаются, а не падают.
    # Тренеру напоминание о занятии приходит как обычно
    channel = FakeChannel()
    await dispatch(channel, datetime(2030, 1, 7, 6, tzinfo=UTC))
    assert channel.sent == [(ADMIN_TELEGRAM_ID, "⏰ Сегодня в 10:00: Мария\nПерсональная")]
    statuses = (
        await session.scalars(
            select(Notification.status).where(Notification.user_id == created["id"])
        )
    ).all()
    assert statuses and set(statuses) == {"skipped"}


async def test_only_own_offline_clients_are_editable(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers, trainer_id, _ = await setup_trainer(client)
    real = await me_id(client, await new_client(client, session, trainer_id, 3003))
    response = await client.patch(
        f"/api/trainer/clients/{real}", headers=headers, json={"first_name": "Чужое"}
    )
    assert response.status_code == 409
    response = await client.post(f"/api/trainer/clients/{real}/claim-link", headers=headers)
    assert response.status_code == 409
    response = await client.patch(
        "/api/trainer/clients/999999", headers=headers, json={"first_name": "Нет"}
    )
    assert response.status_code == 404


async def test_new_telegram_user_claims_history(client: AsyncClient, session: AsyncSession) -> None:
    headers, trainer_id, service_id = await setup_trainer(client)
    offline = await add_client(client, headers, notes="колено")
    booking_id = await trainer_books(client, headers, offline["id"], service_id)
    response = await sell(client, headers, offline["id"])
    package_id = response["id"]
    code = await claim_code(client, headers, offline["id"])
    # Повторный запрос ссылки отдаёт ту же ссылку
    assert await claim_code(client, headers, offline["id"]) == code

    user = await make_user(session, 7007, "Маша")
    trainer = await claim(session, user, code, datetime.now(UTC))
    assert trainer.id == trainer_id

    session.expire_all()
    assert await session.get(User, offline["id"]) is None
    booking = await session.get(Booking, booking_id)
    package = await session.get(Package, package_id)
    assert booking is not None and booking.client_id == user.id
    assert package is not None and package.client_id == user.id
    link = await session.scalar(select(TrainerClient).where(TrainerClient.user_id == user.id))
    assert link is not None and link.notes == "колено" and link.claim_code is None
    # Имя — то, что у человека в Telegram
    clients = (await client.get("/api/trainer/clients", headers=headers)).json()
    assert [(c["id"], c["first_name"], c["offline"]) for c in clients] == [(user.id, "Маша", False)]
    # Напоминания теперь стоят ему
    reminders = (
        await session.scalars(
            select(Notification.status).where(
                Notification.user_id == user.id,
                Notification.kind == "reminder",
                Notification.booking_id == booking_id,
            )
        )
    ).all()
    assert reminders == ["pending", "pending"]

    with pytest.raises(LinkRejected) as used:
        await claim(session, user, code, datetime.now(UTC))
    assert used.value.reason is LinkError.NOT_FOUND


async def test_existing_client_claims_and_cards_merge(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers, trainer_id, service_id = await setup_trainer(client)
    offline = await add_client(client, headers, notes="старая карточка")
    real_headers = await new_client(client, session, trainer_id, 3003)
    real = await me_id(client, real_headers)
    await client.put(
        f"/api/trainer/clients/{real}/notes", headers=headers, json={"notes": "из Telegram"}
    )
    # Тренер записал на одно и то же занятие обе карточки
    await trainer_books(client, headers, offline["id"], service_id)
    await trainer_books(client, headers, real, service_id, ELEVEN)
    await trainer_books(client, headers, offline["id"], service_id, "2030-01-14T07:00:00Z")
    await client.post(
        f"/api/trainer/clients/{offline['id']}/measurements",
        headers=headers,
        json={"day": "2030-01-01", "kind": "weight", "value": 80},
    )
    code = await claim_code(client, headers, offline["id"])

    user = await session.get(User, real)
    assert user is not None
    await claim(session, user, code, datetime.now(UTC))

    session.expire_all()
    links = (
        await session.scalars(select(TrainerClient).where(TrainerClient.trainer_id == trainer_id))
    ).all()
    assert [(link.user_id, link.notes) for link in links] == [
        (real, "из Telegram\n\nстарая карточка")
    ]
    mine = (await client.get("/api/client/bookings", headers=real_headers)).json()
    assert sorted(b["starts_at"] for b in mine) == [
        "2030-01-07T07:00:00Z",
        "2030-01-07T08:00:00Z",
        "2030-01-14T07:00:00Z",
    ]
    # Замеры старой карточки не потерялись
    progress = (await client.get("/api/client/progress", headers=real_headers)).json()
    assert [p["value"] for p in progress[0]["series"][0]["points"]] == [80]


async def test_duplicate_booking_is_cancelled_on_merge(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers, trainer_id, _ = await setup_trainer(client)
    # Групповое занятие: обе карточки записаны на одно и то же время
    group = await create_service(client, headers, name="Группа", capacity=5)
    offline = await add_client(client, headers)
    real = await me_id(client, await new_client(client, session, trainer_id, 3003))
    await trainer_books(client, headers, offline["id"], group)
    await trainer_books(client, headers, real, group)

    response = await client.post(
        f"/api/trainer/clients/{offline['id']}/merge", headers=headers, json={"into_id": real}
    )
    assert response.status_code == 204, response.text
    session.expire_all()
    rows = (
        await session.execute(select(Booking.client_id, Booking.status).order_by(Booking.id))
    ).all()
    assert [tuple(r) for r in rows] == [(real, "cancelled"), (real, "confirmed")]


async def test_merge_rules(client: AsyncClient, session: AsyncSession) -> None:
    headers, trainer_id, _ = await setup_trainer(client)
    first = await add_client(client, headers)
    second = await add_client(client, headers, first_name="Пётр")

    # С другой карточкой без Telegram не склеиваем
    response = await client.post(
        f"/api/trainer/clients/{first['id']}/merge",
        headers=headers,
        json={"into_id": second["id"]},
    )
    assert response.status_code == 409
    # Человек, который не клиент тренера, — не найден
    outsider = await make_user(session, 4004, "Чужой")
    response = await client.post(
        f"/api/trainer/clients/{first['id']}/merge",
        headers=headers,
        json={"into_id": outsider.id},
    )
    assert response.status_code == 404

    # Сам тренер не может забрать карточку своего клиента
    code = await claim_code(client, headers, first["id"])
    trainer = await trainer_row(session, trainer_id)
    owner = await session.get(User, trainer.user_id)
    assert owner is not None
    with pytest.raises(LinkRejected) as own:
        await claim(session, owner, code, datetime.now(UTC))
    assert own.value.reason is LinkError.OWN_LINK
