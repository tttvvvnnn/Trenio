"""Комментарий к отмене, перенос записи и запись тренером вне расписания."""

from datetime import UTC, datetime, time, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import ADMIN_TELEGRAM_ID
from tests.test_bookings import ELEVEN, TEN, book, new_client, setup_trainer, slot_starts
from tests.test_notifications import CLIENT_TG, START, FakeChannel, dispatch, reminder_times
from tests.test_schedule_api import MONDAY, Headers
from tests.test_trainers import make_user
from trenio.services import bookings, schedule
from trenio.services.bookings import Actor, BookingError, BookingRejected
from trenio.services.clients import link_client
from trenio.services.trainers import ensure_admin_is_trainer

# Пн 7 янв 2030, 15:00 по Москве: вне рабочих часов 10–12
OUTSIDE = "2030-01-07T12:00:00Z"
ELEVEN_AT = START + timedelta(hours=1)


async def me_id(client: AsyncClient, headers: Headers) -> int:
    return int((await client.get("/api/me", headers=headers)).json()["id"])


async def sent_now(channel: FakeChannel) -> list[tuple[int | None, str]]:
    channel.sent.clear()
    await dispatch(channel, datetime.now(UTC))
    return channel.sent


async def test_cancel_and_decline_comments(client: AsyncClient, session: AsyncSession) -> None:
    trainer_headers, trainer_id, service_id = await setup_trainer(client)
    headers = await new_client(client, session, trainer_id, CLIENT_TG)
    _, first = await book(client, headers, trainer_id, service_id)
    channel = FakeChannel()
    await sent_now(channel)

    response = await client.post(
        f"/api/client/bookings/{first['id']}/cancel",
        headers=headers,
        json={"comment": "  Заболел, простите  "},
    )
    assert response.status_code == 200, response.text
    assert response.json()["cancel_comment"] == "Заболел, простите"
    assert await sent_now(channel) == [
        (
            ADMIN_TELEGRAM_ID,
            "❌ Иван отменил(а) запись\nПерсональная · пн, 7 янв, 10:00\n"
            "Комментарий: Заболел, простите",
        )
    ]

    # Пустой комментарий — это без комментария
    _, second = await book(client, headers, trainer_id, service_id, ELEVEN)
    await sent_now(channel)
    response = await client.post(
        f"/api/trainer/bookings/{second['id']}/cancel",
        headers=trainer_headers,
        json={"comment": "   "},
    )
    assert response.json()["cancel_comment"] is None
    assert await sent_now(channel) == [
        (CLIENT_TG, "❌ Тренер Иван отменил запись\nПерсональная · пн, 7 янв, 11:00")
    ]

    await client.patch("/api/trainer/me", headers=trainer_headers, json={"auto_confirm": False})
    _, third = await book(client, headers, trainer_id, service_id)
    await sent_now(channel)
    response = await client.post(
        f"/api/trainer/bookings/{third['id']}/decline",
        headers=trainer_headers,
        json={"comment": "Давайте в 11"},
    )
    assert response.json()["cancel_comment"] == "Давайте в 11"
    assert await sent_now(channel) == [
        (
            CLIENT_TG,
            "Тренер Иван не сможет провести занятие в это время\n"
            "Персональная · пн, 7 янв, 10:00\nКомментарий: Давайте в 11\n"
            "Выберите другое окошко в приложении.",
        )
    ]
    # Слишком длинный комментарий не принимаем
    _, fourth = await book(client, headers, trainer_id, service_id)
    response = await client.post(
        f"/api/client/bookings/{fourth['id']}/cancel", headers=headers, json={"comment": "a" * 501}
    )
    assert response.status_code == 422


async def test_client_reschedules(client: AsyncClient, session: AsyncSession) -> None:
    trainer_headers, trainer_id, service_id = await setup_trainer(client)
    headers = await new_client(client, session, trainer_id, CLIENT_TG)
    _, booking = await book(client, headers, trainer_id, service_id)
    channel = FakeChannel()
    await sent_now(channel)
    # Напоминание «за сутки» уже ушло: после переноса оно должно прийти о новом времени
    await dispatch(channel, START - timedelta(hours=23))
    assert [text.splitlines()[0] for _, text in channel.sent][-1].startswith("⏰")

    # Для переноса своё время тоже показывается свободным
    slots = await client.get(
        f"/api/client/trainers/{trainer_id}/slots",
        headers=headers,
        params={
            "from": MONDAY,
            "days": 1,
            "service_id": service_id,
            "reschedule": int(str(booking["id"])),
        },
    )
    # Шаг начала 15 минут: 10:00, 10:15, … 11:00, в том числе внахлёст со своим временем
    assert [s["starts_at"] for s in slots.json()][::4] == [TEN, ELEVEN]

    url = f"/api/client/bookings/{booking['id']}/reschedule"
    response = await client.post(url, headers=headers, json={"starts_at": TEN})
    assert response.status_code == 409
    assert response.json()["detail"] == "Запись уже стоит на это время."
    # Клиент переносит только в окошко расписания
    response = await client.post(url, headers=headers, json={"starts_at": OUTSIDE})
    assert response.status_code == 409

    response = await client.post(
        url, headers=headers, json={"starts_at": ELEVEN, "comment": "Пробки"}
    )
    assert response.status_code == 200, response.text
    moved = response.json()
    assert moved["id"] == booking["id"]
    assert moved["status"] == "confirmed"
    assert moved["starts_at"] == "2030-01-07T08:00:00Z"
    assert moved["rescheduled_from"] == "2030-01-07T07:00:00Z"
    assert moved["rescheduled_by"] == "client"
    assert moved["reschedule_comment"] == "Пробки"
    assert await slot_starts(client, trainer_headers) == [(TEN, 1)]
    assert await reminder_times(session) == [
        ELEVEN_AT - timedelta(days=1),
        ELEVEN_AT - timedelta(hours=2),
    ]
    assert await sent_now(channel) == [
        (
            ADMIN_TELEGRAM_ID,
            "🔁 Иван перенёс(ла) запись\nПерсональная\n"
            "Было: пн, 7 янв, 10:00\nСтало: пн, 7 янв, 11:00\nКомментарий: Пробки",
        )
    ]

    # Чужую запись не перенести и её время не освободить
    stranger = await new_client(client, session, trainer_id, 3009)
    response = await client.post(
        f"/api/client/bookings/{booking['id']}/reschedule",
        headers=stranger,
        json={"starts_at": TEN},
    )
    assert response.status_code == 404
    slots = await client.get(
        f"/api/client/trainers/{trainer_id}/slots",
        headers=stranger,
        params={"reschedule": int(str(booking["id"]))},
    )
    assert slots.status_code == 404


async def test_reschedule_needs_confirmation(client: AsyncClient, session: AsyncSession) -> None:
    trainer_headers, trainer_id, service_id = await setup_trainer(client)
    headers = await new_client(client, session, trainer_id, CLIENT_TG)
    _, booking = await book(client, headers, trainer_id, service_id)
    await client.patch("/api/trainer/me", headers=trainer_headers, json={"auto_confirm": False})
    channel = FakeChannel()
    await sent_now(channel)

    response = await client.post(
        f"/api/client/bookings/{booking['id']}/reschedule",
        headers=headers,
        json={"starts_at": ELEVEN},
    )
    # Без автоподтверждения перенос снова ждёт тренера, напоминаний пока нет
    assert response.json()["status"] == "pending"
    assert await reminder_times(session) == []
    sent = await sent_now(channel)
    assert sent[0][1].startswith("🔁 Иван перенёс(ла) запись, ждёт подтверждения")
    buttons = [button.text for row in channel.messages[-1].buttons for button in row]
    assert buttons[:2] == ["Подтвердить", "Отклонить"]

    # Подтверждение после переноса снова приходит клиенту
    await client.post(f"/api/trainer/bookings/{booking['id']}/confirm", headers=trainer_headers)
    assert await sent_now(channel) == [
        (CLIENT_TG, "✅ Тренер Иван подтвердил запись\nПерсональная · пн, 7 янв, 11:00")
    ]
    assert len(await reminder_times(session)) == 2


async def test_trainer_books_and_moves_any_time(client: AsyncClient, session: AsyncSession) -> None:
    trainer_headers, trainer_id, service_id = await setup_trainer(client)
    headers = await new_client(client, session, trainer_id, CLIENT_TG)
    client_id = await me_id(client, headers)
    other = await me_id(client, await new_client(client, session, trainer_id, 3004))

    # Вне рабочих часов тренер записывает сам
    body = {"client_id": client_id, "service_id": service_id, "starts_at": OUTSIDE}
    response = await client.post("/api/trainer/bookings", headers=trainer_headers, json=body)
    assert response.status_code == 201, response.text
    booking = response.json()
    # Но не туда, где он уже занят, и не в прошлое
    response = await client.post(
        "/api/trainer/bookings",
        headers=trainer_headers,
        json={**body, "client_id": other, "starts_at": "2030-01-07T12:30:00Z"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "В это время у вас другое занятие."
    response = await client.post(
        "/api/trainer/bookings",
        headers=trainer_headers,
        json={**body, "client_id": other, "starts_at": "2020-01-06T12:00:00Z"},
    )
    assert response.status_code == 409

    channel = FakeChannel()
    await sent_now(channel)
    response = await client.post(
        f"/api/trainer/bookings/{booking['id']}/reschedule",
        headers=trainer_headers,
        json={"starts_at": "2030-01-08T16:00:00Z", "comment": "Зал закрыт"},
    )
    assert response.status_code == 200, response.text
    moved = response.json()
    assert moved["status"] == "confirmed" and moved["rescheduled_by"] == "trainer"
    assert await sent_now(channel) == [
        (
            CLIENT_TG,
            "🔁 Тренер Иван перенёс запись\nПерсональная\n"
            "Было: пн, 7 янв, 15:00\nСтало: вт, 8 янв, 19:00\nКомментарий: Зал закрыт",
        )
    ]
    # Освободившееся время можно занять
    response = await client.post(
        "/api/trainer/bookings",
        headers=trainer_headers,
        json={**body, "client_id": other, "starts_at": "2030-01-07T12:30:00Z"},
    )
    assert response.status_code == 201


async def test_group_outside_schedule(client: AsyncClient, session: AsyncSession) -> None:
    trainer_headers, trainer_id, service_id = await setup_trainer(client, name="Сплит", capacity=2)
    ids = [
        await me_id(client, await new_client(client, session, trainer_id, 3000 + i))
        for i in range(3)
    ]

    def body(client_id: int) -> dict[str, object]:
        return {"client_id": client_id, "service_id": service_id, "starts_at": OUTSIDE}

    for client_id in ids[:2]:
        response = await client.post(
            "/api/trainer/bookings", headers=trainer_headers, json=body(client_id)
        )
        assert response.status_code == 201, response.text
    # Групповое вне расписания дополняется до вместимости, дальше мест нет
    response = await client.post(
        "/api/trainer/bookings", headers=trainer_headers, json=body(ids[2])
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Это время уже занято. Выберите другое окошко."


async def test_client_reschedule_window(session: AsyncSession) -> None:
    """Клиент переносит по тем же правилам, что и отменяет."""
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
    eleven = ten + timedelta(hours=1)
    booking = await bookings.create_booking(
        session, trainer, user, service.id, ten, Actor.CLIENT, ten - timedelta(days=2)
    )
    late = ten - timedelta(hours=11)
    with pytest.raises(BookingRejected) as rejected:
        await bookings.reschedule_booking(session, booking, eleven, Actor.CLIENT, late)
    assert rejected.value.reason is BookingError.TOO_LATE_TO_CANCEL
    moved = await bookings.reschedule_booking(session, booking, eleven, Actor.TRAINER, late)
    assert moved.starts_at == eleven and moved.rescheduled_from == ten
    cancelled = await bookings.cancel_booking(session, moved, Actor.TRAINER, late)
    with pytest.raises(BookingRejected) as wrong:
        await bookings.reschedule_booking(session, cancelled, ten, Actor.TRAINER, late)
    assert wrong.value.reason is BookingError.WRONG_STATUS
