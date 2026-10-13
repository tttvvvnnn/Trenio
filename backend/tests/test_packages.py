"""Блоки, платежи, отметки посещений и карточка клиента."""

import asyncio
import contextlib
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_bookings import TEN, book, new_client, setup_trainer
from tests.test_schedule_api import Headers, auth, create_service, second_trainer
from trenio.db.models import Booking, Package
from trenio.services import packages
from trenio.services.packages import Attendance

TEN_FOR_20K = {"name": "10 персональных", "sessions_count": 10, "price": 20000}


async def client_id_of(client: AsyncClient, headers: Headers) -> int:
    me = (await client.get("/api/me", headers=headers)).json()
    user_id: int = me["id"]
    return user_id


async def past_booking(
    session: AsyncSession,
    trainer_id: int,
    client_id: int,
    service_id: int,
    days_ago: int,
    status: str = "confirmed",
) -> int:
    """Прошедшая запись. Через API в прошлое не записаться, поэтому сразу в базу."""
    starts_at = datetime.now(UTC).replace(microsecond=0) - timedelta(days=days_ago)
    booking = Booking(
        trainer_id=trainer_id,
        client_id=client_id,
        service_id=service_id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        status=status,
        created_by="client",
    )
    session.add(booking)
    await session.commit()
    return booking.id


async def sell(
    client: AsyncClient, headers: Headers, client_id: int, **fields: object
) -> dict[str, Any]:
    response = await client.post(
        f"/api/trainer/clients/{client_id}/packages",
        headers=headers,
        json={**TEN_FOR_20K, **fields},
    )
    assert response.status_code == 201, response.text
    package: dict[str, Any] = response.json()
    return package


async def mark(
    client: AsyncClient, headers: Headers, booking_id: int, attendance: str | None
) -> tuple[int, dict[str, Any]]:
    response = await client.post(
        f"/api/trainer/bookings/{booking_id}/attendance",
        headers=headers,
        json={"attendance": attendance},
    )
    return response.status_code, response.json()


async def get_package(client: AsyncClient, headers: Headers, client_id: int) -> dict[str, Any]:
    card = (await client.get(f"/api/trainer/clients/{client_id}", headers=headers)).json()
    package: dict[str, Any] = card["packages"][0]
    return package


async def test_ten_for_20000_paid_10000_used_3(client: AsyncClient, session: AsyncSession) -> None:
    """Готовность этапа: «10 за 20 000, внесено 10 000, пройдено 3» у тренера и у клиента."""
    headers, trainer_id, service_id = await setup_trainer(client)
    client_headers = await new_client(client, session, trainer_id, 3003)
    client_id = await client_id_of(client, client_headers)

    response = await client.post(
        "/api/trainer/package-templates",
        headers=headers,
        json={**TEN_FOR_20K, "service_id": service_id, "valid_days": 60},
    )
    assert response.status_code == 201, response.text
    template = response.json()
    assert template["service"] == {"id": service_id, "name": "Персональная"}

    package = await sell(client, headers, client_id, service_id=service_id)
    response = await client.post(
        f"/api/trainer/packages/{package['id']}/payments",
        headers=headers,
        json={"amount": 10000, "paid_on": "2026-10-05", "comment": "наличные"},
    )
    assert response.status_code == 201, response.text

    ids = [
        await past_booking(session, trainer_id, client_id, service_id, days)
        for days in (7, 5, 3, 1)
    ]
    assert (await mark(client, headers, ids[0], "attended"))[0] == 200
    assert (await mark(client, headers, ids[1], "attended"))[0] == 200
    code, missed = await mark(client, headers, ids[2], "missed_charged")
    assert code == 200, missed
    assert missed["charge"] == {
        "package_id": package["id"],
        "package_name": "10 персональных",
        "number": 3,
        "sessions_count": 10,
    }
    assert missed["one_off"] is False
    # Пропуск без списания занятие не тратит
    code, free = await mark(client, headers, ids[3], "missed_free")
    assert code == 200
    assert free["charge"] is None and free["one_off"] is False

    expected = {
        "sessions_count": 10,
        "price": 20000,
        "paid": 10000,
        "due": 10000,
        "used": 3,
        "left": 7,
        "status": "active",
        "ending_soon": False,
    }
    trainer_view = await get_package(client, headers, client_id)
    assert {key: trainer_view[key] for key in expected} == expected
    assert [(s["number"], s["status"]) for s in trainer_view["sessions"]] == [
        (1, "attended"),
        (2, "attended"),
        (3, "missed_charged"),
    ]
    assert trainer_view["payments"][0]["comment"] == "наличные"

    mine = (await client.get("/api/client/packages", headers=client_headers)).json()
    assert len(mine) == 1
    assert {key: mine[0][key] for key in expected} == expected
    assert mine[0]["trainer"]["id"] == trainer_id

    clients = (await client.get("/api/trainer/clients", headers=headers)).json()
    assert [(c["sessions_left"], c["debt"], c["has_packages"]) for c in clients] == [
        (7, 10000, True)
    ]


async def test_oldest_matching_package(client: AsyncClient, session: AsyncSession) -> None:
    headers, trainer_id, personal = await setup_trainer(client)
    split = await create_service(client, headers, name="Сплит", capacity=2)
    client_headers = await new_client(client, session, trainer_id, 3003)
    client_id = await client_id_of(client, client_headers)
    long_ago = (date.today() - timedelta(days=30)).isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    # Самый старый, но для другой услуги
    only_split = await sell(client, headers, client_id, service_id=split, purchased_on=long_ago)
    # Старый, но истёк до занятий
    expired = await sell(client, headers, client_id, purchased_on=long_ago, valid_until=long_ago)
    # Закрыт тренером
    closed = await sell(client, headers, client_id, purchased_on=long_ago)
    response = await client.patch(
        f"/api/trainer/packages/{closed['id']}", headers=headers, json={"closed": True}
    )
    assert response.json()["status"] == "closed"
    # Подходят оба, но первым должен списываться более старый
    older = await sell(client, headers, client_id, sessions_count=1, purchased_on=yesterday)
    newer = await sell(client, headers, client_id, sessions_count=1)

    first, second, third = [
        await past_booking(session, trainer_id, client_id, personal, days) for days in (3, 2, 1)
    ]
    assert (await mark(client, headers, first, "attended"))[1]["charge"]["package_id"] == older[
        "id"
    ]
    assert (await mark(client, headers, second, "attended"))[1]["charge"]["package_id"] == newer[
        "id"
    ]
    # Подходящих блоков с занятиями больше нет: занятие разовое
    code, one_off = await mark(client, headers, third, "attended")
    assert code == 200
    assert one_off["charge"] is None and one_off["one_off"] is True

    card = (await client.get(f"/api/trainer/clients/{client_id}", headers=headers)).json()
    by_id = {p["id"]: p for p in card["packages"]}
    assert by_id[only_split["id"]]["used"] == 0
    assert by_id[expired["id"]]["status"] == "expired"
    assert by_id[closed["id"]]["used"] == 0
    assert by_id[older["id"]]["status"] == "finished"
    assert by_id[older["id"]]["ending_soon"] is False
    assert [b["one_off"] for b in card["history"]] == [True, False, False]


async def test_change_and_unmark(client: AsyncClient, session: AsyncSession) -> None:
    headers, trainer_id, service_id = await setup_trainer(client)
    client_headers = await new_client(client, session, trainer_id, 3003)
    client_id = await client_id_of(client, client_headers)
    package = await sell(client, headers, client_id, sessions_count=3)
    booking_id = await past_booking(session, trainer_id, client_id, service_id, 1)

    await mark(client, headers, booking_id, "attended")
    code, changed = await mark(client, headers, booking_id, "missed_charged")
    assert code == 200
    assert changed["attendance"] == "missed_charged"
    assert changed["charge"]["number"] == 1
    current = await get_package(client, headers, client_id)
    assert [s["status"] for s in current["sessions"]] == ["missed_charged"]
    assert current["left"] == 2 and current["ending_soon"] is True

    # «Не списывать» и снятие отметки возвращают занятие в блок
    await mark(client, headers, booking_id, "missed_free")
    assert (await get_package(client, headers, client_id))["used"] == 0
    await mark(client, headers, booking_id, "attended")
    code, unmarked = await mark(client, headers, booking_id, None)
    assert code == 200
    assert unmarked["attendance"] is None and unmarked["charge"] is None
    assert (await get_package(client, headers, client_id))["used"] == 0

    # Занятие, списанное за запись, нельзя удалить из блока вручную
    await mark(client, headers, booking_id, "attended")
    session_id = (await get_package(client, headers, client_id))["sessions"][0]["id"]
    response = await client.delete(
        f"/api/trainer/packages/{package['id']}/sessions/{session_id}", headers=headers
    )
    assert response.status_code == 409


async def test_mark_rules(client: AsyncClient, session: AsyncSession) -> None:
    headers, trainer_id, service_id = await setup_trainer(client)
    client_headers = await new_client(client, session, trainer_id, 3003)
    client_id = await client_id_of(client, client_headers)
    await sell(client, headers, client_id)

    # Будущее занятие отмечать рано
    code, future = await book(client, client_headers, trainer_id, service_id, TEN)
    assert code == 201
    assert future["can_mark"] is False
    assert future["attendance"] is None
    assert isinstance(future["id"], int)
    assert (await mark(client, headers, future["id"], "attended"))[0] == 409

    # Позднюю отмену можно списать как пропуск, но не как «прошла»
    cancelled = await past_booking(
        session, trainer_id, client_id, service_id, 1, status="cancelled"
    )
    assert (await mark(client, headers, cancelled, "attended"))[0] == 409
    code, charged = await mark(client, headers, cancelled, "missed_charged")
    assert code == 200 and charged["charge"] is not None

    declined = await past_booking(session, trainer_id, client_id, service_id, 2, status="declined")
    assert (await mark(client, headers, declined, "missed_free"))[0] == 409

    # Неподтверждённое прошедшее занятие после отметки считается подтверждённым
    pending = await past_booking(session, trainer_id, client_id, service_id, 3, status="pending")
    code, confirmed = await mark(client, headers, pending, "attended")
    assert code == 200 and confirmed["status"] == "confirmed"

    # Чужой тренер не видит ни запись, ни клиента
    other = await second_trainer(client, session)
    assert (await mark(client, other, pending, None))[0] == 404
    response = await client.get(f"/api/trainer/clients/{client_id}", headers=other)
    assert response.status_code == 404


async def test_unmarked_and_one_off_forecast(client: AsyncClient, session: AsyncSession) -> None:
    headers, trainer_id, service_id = await setup_trainer(client)
    client_headers = await new_client(client, session, trainer_id, 3003)
    client_id = await client_id_of(client, client_headers)
    old = await past_booking(session, trainer_id, client_id, service_id, 2)
    fresh = await past_booking(session, trainer_id, client_id, service_id, 1)
    await past_booking(session, trainer_id, client_id, service_id, 100)
    await past_booking(session, trainer_id, client_id, service_id, 1, status="cancelled")

    response = await client.get("/api/trainer/bookings/unmarked", headers=headers)
    assert response.status_code == 200, response.text
    found = response.json()
    assert [b["id"] for b in found] == [fresh, old]
    # Блока нет: запись будет разовой
    assert all(b["one_off"] for b in found)

    await sell(client, headers, client_id)
    found = (await client.get("/api/trainer/bookings/unmarked", headers=headers)).json()
    assert not any(b["one_off"] for b in found)

    await mark(client, headers, fresh, "missed_free")
    found = (await client.get("/api/trainer/bookings/unmarked", headers=headers)).json()
    assert [b["id"] for b in found] == [old]


async def test_package_editing(client: AsyncClient, session: AsyncSession) -> None:
    headers, trainer_id, service_id = await setup_trainer(client)
    client_headers = await new_client(client, session, trainer_id, 3003)
    client_id = await client_id_of(client, client_headers)
    package = await sell(client, headers, client_id, sessions_count=2, price=5000)
    url = f"/api/trainer/packages/{package['id']}"

    # Блок без списаний удаляется
    other = await sell(client, headers, client_id)
    response = await client.delete(f"/api/trainer/packages/{other['id']}", headers=headers)
    assert response.status_code == 204

    response = await client.post(f"{url}/sessions", headers=headers, json={"day": "2026-10-01"})
    assert response.status_code == 201, response.text
    response = await client.post(
        f"{url}/sessions",
        headers=headers,
        json={"day": "2026-09-01", "attendance": "missed_charged"},
    )
    current = response.json()
    # Номера идут по датам, а не по порядку отметок
    assert [(s["number"], s["day"]) for s in current["sessions"]] == [
        (1, "2026-09-01"),
        (2, "2026-10-01"),
    ]
    response = await client.post(f"{url}/sessions", headers=headers, json={"day": "2026-10-02"})
    assert response.status_code == 409
    response = await client.post(
        f"{url}/sessions", headers=headers, json={"day": "2026-10-02", "attendance": "missed_free"}
    )
    assert response.status_code == 409

    response = await client.patch(url, headers=headers, json={"sessions_count": 1})
    assert response.status_code == 409
    response = await client.patch(
        url, headers=headers, json={"sessions_count": 4, "name": "4 занятия", "price": 8000}
    )
    assert response.status_code == 200, response.text
    assert response.json()["left"] == 2
    response = await client.patch(
        url, headers=headers, json={"purchased_on": "2026-10-10", "valid_until": "2026-10-01"}
    )
    assert response.status_code == 422
    response = await client.delete(url, headers=headers)
    assert response.status_code == 409

    manual_id = current["sessions"][0]["id"]
    response = await client.delete(f"{url}/sessions/{manual_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["used"] == 1

    payment = (await client.post(f"{url}/payments", headers=headers, json={"amount": 3000})).json()
    assert payment["paid"] == 3000 and payment["due"] == 5000
    # Переплата не превращается в отрицательный долг
    paid = (await client.post(f"{url}/payments", headers=headers, json={"amount": 9000})).json()
    assert paid["due"] == 0
    response = await client.delete(f"{url}/payments/{paid['payments'][0]['id']}", headers=headers)
    assert response.json()["paid"] == 9000


async def test_templates_and_notes(client: AsyncClient, session: AsyncSession) -> None:
    headers, trainer_id, service_id = await setup_trainer(client)
    client_headers = await new_client(client, session, trainer_id, 3003)
    client_id = await client_id_of(client, client_headers)

    response = await client.post(
        "/api/trainer/package-templates", headers=headers, json={**TEN_FOR_20K, "service_id": 999}
    )
    assert response.status_code == 422
    template = (
        await client.post("/api/trainer/package-templates", headers=headers, json=TEN_FOR_20K)
    ).json()
    assert template["service"] is None
    response = await client.put(
        f"/api/trainer/package-templates/{template['id']}",
        headers=headers,
        json={**TEN_FOR_20K, "service_id": service_id, "sessions_count": 5},
    )
    assert response.json()["service"]["id"] == service_id
    assert response.json()["sessions_count"] == 5
    other = await second_trainer(client, session)
    assert (await client.get("/api/trainer/package-templates", headers=other)).json() == []
    response = await client.delete(
        f"/api/trainer/package-templates/{template['id']}", headers=headers
    )
    assert response.status_code == 204
    assert (await client.get("/api/trainer/package-templates", headers=headers)).json() == []

    response = await client.put(
        f"/api/trainer/clients/{client_id}/notes", headers=headers, json={"notes": " колено "}
    )
    assert response.json() == {"notes": "колено"}
    card = (await client.get(f"/api/trainer/clients/{client_id}", headers=headers)).json()
    assert card["notes"] == "колено"
    assert card["client"]["sessions_left"] is None and card["client"]["has_packages"] is False

    # Блок можно продать только своему клиенту
    stranger = await client_id_of(client, await auth(client, 4004))
    response = await client.post(
        f"/api/trainer/clients/{stranger}/packages", headers=headers, json=TEN_FOR_20K
    )
    assert response.status_code == 404


async def test_parallel_marks_do_not_overdraw(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Два занятия отмечают одновременно, а в блоке одно место: списывается только одно."""
    from trenio.db.session import get_sessionmaker

    # Без блокировки обе транзакции дошли бы сюда вместе и выбрали один и тот же блок.
    # С блокировкой вторая ждёт в базе, а первая через полсекунды идёт дальше одна
    barrier = asyncio.Barrier(2)
    pick = packages._pick_package

    async def pick_together(own: AsyncSession, booking: Booking) -> Package | None:
        found = await pick(own, booking)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(barrier.wait(), 0.5)
        return found

    monkeypatch.setattr(packages, "_pick_package", pick_together)

    headers, trainer_id, service_id = await setup_trainer(client)
    client_headers = await new_client(client, session, trainer_id, 3003)
    client_id = await client_id_of(client, client_headers)
    await sell(client, headers, client_id, sessions_count=1)
    ids = [await past_booking(session, trainer_id, client_id, service_id, d) for d in (2, 1)]

    async def mark_in_own_session(booking_id: int) -> None:
        async with get_sessionmaker()() as own:
            booking = await own.get(Booking, booking_id)
            assert booking is not None
            await packages.mark_attendance(own, booking, Attendance.ATTENDED, datetime.now(UTC))

    await asyncio.gather(*(mark_in_own_session(booking_id) for booking_id in ids))
    package = await get_package(client, headers, client_id)
    assert package["used"] == 1
    card = (await client.get(f"/api/trainer/clients/{client_id}", headers=headers)).json()
    assert sorted(b["one_off"] for b in card["history"]) == [False, True]


async def test_forecast_of_future_bookings(client: AsyncClient, session: AsyncSession) -> None:
    """Будущие записи раскладываются по остатку блока, лишние — разовые."""
    headers, trainer_id, service_id = await setup_trainer(client)
    client_headers = await new_client(client, session, trainer_id, 3003)
    client_id = await client_id_of(client, client_headers)
    package = await sell(client, headers, client_id, sessions_count=3)
    done = await past_booking(session, trainer_id, client_id, service_id, 2)
    assert (await mark(client, headers, done, "attended"))[0] == 200
    # Отрицательный days_ago — запись в будущем
    first, second, third = [
        await past_booking(session, trainer_id, client_id, service_id, -days) for days in (1, 2, 3)
    ]

    card = (await client.get(f"/api/trainer/clients/{client_id}", headers=headers)).json()
    assert card["client"]["sessions_left"] == 2
    assert card["client"]["upcoming_one_off"] == 1
    assert [(p["booking_id"], p["number"]) for p in card["packages"][0]["planned"]] == [
        (first, 2),
        (second, 3),
    ]
    history = {b["id"]: b for b in card["history"]}
    assert history[first]["planned"]["number"] == 2
    assert history[first]["one_off"] is False
    assert history[third]["planned"] is None
    assert history[third]["one_off"] is True
    assert history[third]["out_of_block"] is True

    clients = (await client.get("/api/trainer/clients", headers=headers)).json()
    assert clients[0]["upcoming_one_off"] == 1

    # Клиент видит те же планы в своих блоках
    mine = (await client.get("/api/client/packages", headers=client_headers)).json()
    assert [p["booking_id"] for p in mine[0]["planned"]] == [first, second]

    # Отдельная запись тренера открывается по id
    response = await client.get(f"/api/trainer/bookings/{third}", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["one_off"] is True

    # Ручное занятие можно исправить
    url = f"/api/trainer/packages/{package['id']}/sessions"
    added = (await client.post(url, headers=headers, json={"day": "2026-10-01"})).json()
    manual = next(s for s in added["sessions"] if s["booking_id"] is None)
    response = await client.patch(
        f"{url}/{manual['id']}",
        headers=headers,
        json={"day": "2026-09-30", "attendance": "missed_charged"},
    )
    assert response.status_code == 200, response.text
    changed = next(s for s in response.json()["sessions"] if s["id"] == manual["id"])
    assert (changed["day"], changed["status"]) == ("2026-09-30", "missed_charged")
    linked = next(s for s in added["sessions"] if s["booking_id"] == done)
    response = await client.patch(
        f"{url}/{linked['id']}", headers=headers, json={"day": "2026-09-30"}
    )
    assert response.status_code == 409

    # После ручного списания в блоке осталось одно место: вторая будущая запись стала разовой
    card = (await client.get(f"/api/trainer/clients/{client_id}", headers=headers)).json()
    assert card["client"]["upcoming_one_off"] == 2


async def test_client_without_packages_is_not_flagged(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Клиент без блоков платит разово: записи разовые, но «блок закончился» не выделяем."""
    headers, trainer_id, service_id = await setup_trainer(client)
    client_headers = await new_client(client, session, trainer_id, 3003)
    client_id = await client_id_of(client, client_headers)
    future = await past_booking(session, trainer_id, client_id, service_id, -1)

    card = (await client.get(f"/api/trainer/clients/{client_id}", headers=headers)).json()
    assert card["client"]["upcoming_one_off"] == 0
    booking = card["history"][0]
    assert (booking["id"], booking["one_off"], booking["out_of_block"]) == (future, True, False)
