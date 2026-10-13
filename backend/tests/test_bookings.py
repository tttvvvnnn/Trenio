"""Клиенты тренера и записи: ссылка, бронирование, отмена, защита от двойной записи."""

import asyncio
from datetime import UTC, datetime, time, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import ADMIN_TELEGRAM_ID
from tests.test_schedule_api import MONDAY, Headers, auth, create_service
from tests.test_trainers import make_user
from trenio.bot.handlers import start_text
from trenio.db.models import Trainer, User
from trenio.services import bookings, schedule
from trenio.services.bookings import Actor, BookingError, BookingRejected
from trenio.services.clients import LinkError, LinkRejected, link_client
from trenio.services.trainers import ensure_admin_is_trainer

# Понедельник 2030-01-07, 10:00–12:00 по Москве = 07:00–09:00 UTC
TEN = "2030-01-07T07:00:00Z"
ELEVEN = "2030-01-07T08:00:00Z"


async def setup_trainer(client: AsyncClient, **service: object) -> tuple[Headers, int, int]:
    """Админ-тренер с услугой и окном по понедельникам 10–12. Возвращает id тренера и услуги."""
    headers = await auth(client)
    service_id = await create_service(client, headers, **service)
    response = await client.post(
        "/api/trainer/schedule/rules",
        headers=headers,
        json={"weekday": 0, "start": "10:00", "end": "12:00"},
    )
    assert response.status_code == 201, response.text
    me = (await client.get("/api/me", headers=headers)).json()
    return headers, me["trainer"]["id"], service_id


async def trainer_row(session: AsyncSession, trainer_id: int) -> Trainer:
    trainer = await session.get(Trainer, trainer_id)
    assert trainer is not None
    await session.refresh(trainer)
    return trainer


async def new_client(
    client: AsyncClient, session: AsyncSession, trainer_id: int, telegram_id: int
) -> Headers:
    """Клиент, который перешёл по ссылке тренера."""
    headers = await auth(client, telegram_id)
    me = (await client.get("/api/me", headers=headers)).json()
    user = await session.get(User, me["id"])
    assert user is not None
    trainer = await trainer_row(session, trainer_id)
    await link_client(session, user, trainer.invite_code)
    return headers


async def book(
    client: AsyncClient, headers: Headers, trainer_id: int, service_id: int, starts_at: str = TEN
) -> tuple[int, dict[str, object]]:
    response = await client.post(
        "/api/client/bookings",
        headers=headers,
        json={"trainer_id": trainer_id, "service_id": service_id, "starts_at": starts_at},
    )
    return response.status_code, response.json()


async def slot_starts(client: AsyncClient, headers: Headers) -> list[tuple[str, int]]:
    response = await client.get(
        "/api/trainer/slots", headers=headers, params={"from": MONDAY, "days": 1}
    )
    assert response.status_code == 200, response.text
    return [(slot["starts_at"], slot["seats_left"]) for slot in response.json()]


async def test_link_client(session: AsyncSession) -> None:
    admin = await make_user(session, ADMIN_TELEGRAM_ID, "Тихон")
    trainer = await ensure_admin_is_trainer(session, admin, {ADMIN_TELEGRAM_ID})
    assert trainer is not None
    user = await make_user(session, 5005, "Анна")

    assert (await link_client(session, user, trainer.invite_code)).id == trainer.id
    # Повторный переход по ссылке не ошибка и не создаёт дубль
    assert (await link_client(session, user, trainer.invite_code)).id == trainer.id

    with pytest.raises(LinkRejected) as own:
        await link_client(session, admin, trainer.invite_code)
    assert own.value.reason is LinkError.OWN_LINK
    with pytest.raises(LinkRejected) as missing:
        await link_client(session, user, "nope")
    assert missing.value.reason is LinkError.NOT_FOUND

    assert "записаться" in start_text("Анна", None, admin=False, has_trainers=True)


async def test_client_sees_trainer_and_books(client: AsyncClient, session: AsyncSession) -> None:
    trainer_headers, trainer_id, service_id = await setup_trainer(client)
    headers = await new_client(client, session, trainer_id, 3003)

    me = (await client.get("/api/me", headers=headers)).json()
    assert me["is_client"] is True and me["is_trainer"] is False
    trainers = (await client.get("/api/client/trainers", headers=headers)).json()
    assert [t["id"] for t in trainers] == [trainer_id]
    services = await client.get(f"/api/client/trainers/{trainer_id}/services", headers=headers)
    assert [s["id"] for s in services.json()] == [service_id]

    code, booking = await book(client, headers, trainer_id, service_id)
    assert code == 201, booking
    assert booking["status"] == "confirmed"
    assert booking["created_by"] == "client"
    assert booking["can_cancel"] is True
    assert booking["service"] == {
        "id": service_id,
        "name": "Персональная",
        "duration_min": 60,
        "capacity": 1,
    }

    # Занятое окошко пропало и у тренера, и у клиента
    assert await slot_starts(client, trainer_headers) == [(ELEVEN, 1)]
    client_slots = await client.get(
        f"/api/client/trainers/{trainer_id}/slots",
        headers=headers,
        params={"from": MONDAY, "days": 1},
    )
    assert [s["starts_at"] for s in client_slots.json()] == [ELEVEN]

    mine = (await client.get("/api/client/bookings", headers=headers)).json()
    assert [b["id"] for b in mine] == [booking["id"]]
    listed = await client.get(
        "/api/trainer/bookings", headers=trainer_headers, params={"from": MONDAY, "days": 1}
    )
    assert [b["client"]["id"] for b in listed.json()] == [me["id"]]

    clients = (await client.get("/api/trainer/clients", headers=trainer_headers)).json()
    assert [c["id"] for c in clients] == [me["id"]]


async def test_stranger_cannot_book(client: AsyncClient) -> None:
    _, trainer_id, service_id = await setup_trainer(client)
    stranger = await auth(client, 4004)
    code, _ = await book(client, stranger, trainer_id, service_id)
    assert code == 404
    slots = await client.get(f"/api/client/trainers/{trainer_id}/slots", headers=stranger)
    assert slots.status_code == 404


async def test_slot_must_exist(client: AsyncClient, session: AsyncSession) -> None:
    _, trainer_id, service_id = await setup_trainer(client)
    headers = await new_client(client, session, trainer_id, 3003)
    # 10:10 не попадает в шаг 15 минут, 11:30 + час вылезает за конец окна в 12:00
    for starts_at in ("2030-01-07T07:10:00Z", "2030-01-07T08:30:00Z"):
        code, body = await book(client, headers, trainer_id, service_id, starts_at)
        assert code == 409, body
    code, _ = await book(client, headers, trainer_id, service_id + 100)
    assert code == 404


async def test_manual_confirmation(client: AsyncClient, session: AsyncSession) -> None:
    trainer_headers, trainer_id, service_id = await setup_trainer(client)
    await client.patch("/api/trainer/me", headers=trainer_headers, json={"auto_confirm": False})
    first = await new_client(client, session, trainer_id, 3003)
    second = await new_client(client, session, trainer_id, 3004)

    code, pending = await book(client, first, trainer_id, service_id)
    assert code == 201 and pending["status"] == "pending"
    # Неподтверждённая запись тоже занимает время
    assert await slot_starts(client, trainer_headers) == [(ELEVEN, 1)]
    code, other = await book(client, second, trainer_id, service_id, ELEVEN)
    assert code == 201

    waiting = (await client.get("/api/trainer/bookings/pending", headers=trainer_headers)).json()
    assert [b["id"] for b in waiting] == [pending["id"], other["id"]]

    confirmed = await client.post(
        f"/api/trainer/bookings/{pending['id']}/confirm", headers=trainer_headers
    )
    assert confirmed.json()["status"] == "confirmed"
    declined = await client.post(
        f"/api/trainer/bookings/{other['id']}/decline", headers=trainer_headers
    )
    assert declined.json()["status"] == "declined"
    # Отклонённая запись освобождает окошко, повторно отклонить нельзя
    assert await slot_starts(client, trainer_headers) == [(ELEVEN, 1)]
    again = await client.post(
        f"/api/trainer/bookings/{other['id']}/decline", headers=trainer_headers
    )
    assert again.status_code == 409


async def test_group_capacity(client: AsyncClient, session: AsyncSession) -> None:
    trainer_headers, trainer_id, service_id = await setup_trainer(client, name="Сплит", capacity=2)
    clients = [await new_client(client, session, trainer_id, 3000 + i) for i in range(3)]

    assert (await book(client, clients[0], trainer_id, service_id))[0] == 201
    assert await slot_starts(client, trainer_headers) == [(TEN, 1), (ELEVEN, 2)]
    # Тот же клиент второй раз на то же занятие не записывается
    assert (await book(client, clients[0], trainer_id, service_id))[0] == 409
    assert (await book(client, clients[1], trainer_id, service_id))[0] == 201
    assert (await book(client, clients[2], trainer_id, service_id))[0] == 409
    assert await slot_starts(client, trainer_headers) == [(ELEVEN, 2)]


async def me_id(client: AsyncClient, headers: Headers) -> int:
    user_id: int = (await client.get("/api/me", headers=headers)).json()["id"]
    return user_id


async def test_two_phones_one_slot(client: AsyncClient, session: AsyncSession) -> None:
    """Критерий готовности этапа: два одновременных запроса, запись получает один."""
    _, trainer_id, service_id = await setup_trainer(client)
    phones = [await new_client(client, session, trainer_id, 3003 + i) for i in range(2)]
    by_user = {await me_id(client, headers): headers for headers in phones}

    for _ in range(3):
        results = await asyncio.gather(
            *(book(client, headers, trainer_id, service_id) for headers in phones)
        )
        assert sorted(code for code, _ in results) == [201, 409], results
        winner = next(body for code, body in results if code == 201)
        # Победитель отменяет запись, и окошко снова разыгрывается
        owner = by_user[winner["client"]["id"]]  # type: ignore[index]
        cancel = await client.post(f"/api/client/bookings/{winner['id']}/cancel", headers=owner)
        assert cancel.status_code == 200, cancel.text


async def test_same_client_twice_at_once(client: AsyncClient, session: AsyncSession) -> None:
    _, trainer_id, service_id = await setup_trainer(client, name="Группа", capacity=5)
    headers = await new_client(client, session, trainer_id, 3003)
    results = await asyncio.gather(
        *(book(client, headers, trainer_id, service_id) for _ in range(3))
    )
    assert sorted(code for code, _ in results) == [201, 409, 409]


async def test_trainer_books_and_cancels(client: AsyncClient, session: AsyncSession) -> None:
    trainer_headers, trainer_id, service_id = await setup_trainer(client)
    await client.patch("/api/trainer/me", headers=trainer_headers, json={"auto_confirm": False})
    headers = await new_client(client, session, trainer_id, 3003)
    client_id = await me_id(client, headers)

    body = {"client_id": client_id, "service_id": service_id, "starts_at": TEN}
    response = await client.post("/api/trainer/bookings", headers=trainer_headers, json=body)
    assert response.status_code == 201, response.text
    booking = response.json()
    # Запись от тренера подтверждена сразу, даже при ручном подтверждении
    assert booking["status"] == "confirmed" and booking["created_by"] == "trainer"

    stranger = await me_id(client, await auth(client, 4004))
    response = await client.post(
        "/api/trainer/bookings",
        headers=trainer_headers,
        json={**body, "client_id": stranger, "starts_at": ELEVEN},
    )
    assert response.status_code == 403

    cancelled = await client.post(
        f"/api/trainer/bookings/{booking['id']}/cancel", headers=trainer_headers
    )
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["cancelled_by"] == "trainer"
    mine = (await client.get("/api/client/bookings", headers=headers)).json()
    assert [(b["status"], b["can_cancel"]) for b in mine] == [("cancelled", False)]


async def test_client_cancel_window(session: AsyncSession) -> None:
    """Клиент отменяет сам, только пока до начала больше cancel_hours тренера."""
    admin = await make_user(session, ADMIN_TELEGRAM_ID, "Тихон")
    trainer = await ensure_admin_is_trainer(session, admin, {ADMIN_TELEGRAM_ID})
    assert trainer is not None
    service = await schedule.create_service(
        session, trainer, schedule.ServiceData("Персональная", 60)
    )
    await schedule.create_rule(session, trainer, schedule.RuleData(0, time(10), time(12)))
    user = await make_user(session, 3003, "Анна")
    await link_client(session, user, trainer.invite_code)

    ten = datetime(2030, 1, 7, 7, tzinfo=UTC)
    early = ten - timedelta(days=2)
    booking = await bookings.create_booking(
        session, trainer, user, service.id, ten, Actor.CLIENT, early
    )
    assert bookings.client_can_cancel(booking, early)
    # За 11 часов до начала при правиле 12 часов уже поздно
    late = ten - timedelta(hours=11)
    assert not bookings.client_can_cancel(booking, late)
    with pytest.raises(BookingRejected) as rejected:
        await bookings.cancel_booking(session, booking, Actor.CLIENT, late)
    assert rejected.value.reason is BookingError.TOO_LATE_TO_CANCEL
    # Тренер может отменить, а после начала уже никто
    with pytest.raises(BookingRejected) as started:
        await bookings.cancel_booking(session, booking, Actor.TRAINER, ten)
    assert started.value.reason is BookingError.STARTED
    cancelled = await bookings.cancel_booking(session, booking, Actor.TRAINER, late)
    assert cancelled.status == "cancelled"


async def test_invite_link(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from trenio.api.routes import bookings as routes

    async def username() -> str:
        return "trenio_test_bot"

    monkeypatch.setattr(routes, "get_bot_username", username)
    headers = await auth(client)
    response = await client.get("/api/trainer/invite-link", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["url"].startswith("https://t.me/trenio_test_bot?start=c_")


async def test_start_step(client: AsyncClient, session: AsyncSession) -> None:
    """По умолчанию начало каждые 15 минут, шаг меняется в профиле тренера."""
    trainer_headers, trainer_id, service_id = await setup_trainer(client)
    starts = [start for start, _ in await slot_starts(client, trainer_headers)]
    assert starts == [
        f"2030-01-07T0{h}:{m:02d}:00Z" for h, m in ((7, 0), (7, 15), (7, 30), (7, 45), (8, 0))
    ]

    headers = await new_client(client, session, trainer_id, 3003)
    code, booking = await book(client, headers, trainer_id, service_id, "2030-01-07T07:15:00Z")
    assert code == 201, booking
    # 10:15–11:15 занято: ни одно часовое занятие в окне 10–12 больше не помещается
    assert await slot_starts(client, trainer_headers) == []

    response = await client.patch(
        "/api/trainer/me", headers=trainer_headers, json={"slot_step_min": 7}
    )
    assert response.status_code == 422
    response = await client.patch(
        "/api/trainer/me", headers=trainer_headers, json={"slot_step_min": 0}
    )
    assert response.json()["slot_step_min"] == 0
