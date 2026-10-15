"""Финансы тренера: получено, отработано, аванс, долги и прогноз."""

from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_bookings import new_client, setup_trainer
from tests.test_packages import client_id_of, mark, sell
from tests.test_schedule_api import Headers
from trenio.db.models import Booking, Service


async def booking_at(
    session: AsyncSession, trainer_id: int, client_id: int, service_id: int, starts_at: datetime
) -> int:
    booking = Booking(
        trainer_id=trainer_id,
        client_id=client_id,
        service_id=service_id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        status="confirmed",
        created_by="client",
        # Как при записи: цена разового занятия копируется из услуги
        price=await session.scalar(select(Service.price).where(Service.id == service_id)),
    )
    session.add(booking)
    await session.commit()
    return booking.id


def noon(day: str) -> datetime:
    return datetime.fromisoformat(f"{day}T12:00:00+00:00")


async def pay(
    client: AsyncClient, headers: Headers, package_id: int, amount: int, day: str
) -> None:
    response = await client.post(
        f"/api/trainer/packages/{package_id}/payments",
        headers=headers,
        json={"amount": amount, "paid_on": day, "comment": None},
    )
    assert response.status_code == 201, response.text


async def get(client: AsyncClient, headers: Headers, path: str, **params: str | int) -> Any:
    response = await client.get(f"/api/trainer/finance/{path}", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def test_finance(client: AsyncClient, session: AsyncSession) -> None:
    headers, trainer_id, service_id = await setup_trainer(client, price=2500)
    anna = await client_id_of(client, await new_client(client, session, trainer_id, 501))
    boris = await client_id_of(client, await new_client(client, session, trainer_id, 502))
    clara = await client_id_of(client, await new_client(client, session, trainer_id, 503))

    # Анна: 10 за 20 000, внесла 10 000 в августе и 5 000 в сентябре, прошла 3 занятия
    big = await sell(client, headers, anna, purchased_on="2026-08-20", valid_until=None)
    await pay(client, headers, big["id"], 10000, "2026-08-20")
    await pay(client, headers, big["id"], 5000, "2026-09-05")
    for day in ("2026-08-25", "2026-09-10", "2026-09-12"):
        booking_id = await booking_at(session, trainer_id, anna, service_id, noon(day))
        assert (await mark(client, headers, booking_id, "attended"))[0] == 200

    # Борис без блоков: разовое прошло, пропуск без списания денег не приносит
    one_off = await booking_at(session, trainer_id, boris, service_id, noon("2026-09-15"))
    assert (await mark(client, headers, one_off, "attended"))[0] == 200
    free = await booking_at(session, trainer_id, boris, service_id, noon("2026-09-16"))
    assert (await mark(client, headers, free, "missed_free"))[0] == 200

    # Клара: 3 за 6 000, оплачено в октябре, осталось одно занятие — пора продлевать
    small = await sell(
        client,
        headers,
        clara,
        name="3 занятия",
        sessions_count=3,
        price=6000,
        purchased_on="2026-09-18",
        valid_until=None,
    )
    await pay(client, headers, small["id"], 6000, "2026-10-01")
    for day in ("2026-09-20", "2026-09-21"):
        booking_id = await booking_at(session, trainer_id, clara, service_id, noon(day))
        assert (await mark(client, headers, booking_id, "missed_charged"))[0] == 200

    # Будущее разовое занятие Бориса через три дня
    soon = datetime.now(UTC).replace(microsecond=0) + timedelta(days=3)
    await booking_at(session, trainer_id, boris, service_id, soon)

    september = await get(client, headers, "summary", month="2026-09")
    assert september["received"] == 5000 + 2500
    assert september["received_prev"] == 10000
    assert september["incomes_count"] == 2
    assert september["from_packages"] == 5000
    assert september["from_one_off"] == 2500
    # 2 занятия Анны по 2 000, разовое Бориса 2 500, 2 занятия Клары по 2 000
    assert september["worked"] == 4000 + 2500 + 4000
    assert september["worked_sessions"] == 5
    assert september["clients"] == 3
    assert september["debt"] == 5000
    assert september["debt_clients"] == 1
    # Анна: 15 000 − 3 × 2 000; Клара: 6 000 − 2 × 2 000
    assert september["advance"] == 9000 + 2000
    # Сентябрь прошёл: впереди в нём ничего нет
    assert september["planned_count"] == 0
    assert [p["month"] for p in september["chart"]] == [
        "2026-04",
        "2026-05",
        "2026-06",
        "2026-07",
        "2026-08",
        "2026-09",
    ]
    assert september["chart"][-2] == {"month": "2026-08", "received": 10000, "worked": 2000}

    year = await get(client, headers, "year", year=2026)
    assert len(year["months"]) == 12
    assert year["received"] == 10000 + 5000 + 2500 + 6000
    assert year["worked"] == 2000 + 10500
    assert year["worked_sessions"] == 6

    details = await get(client, headers, "month", month="2026-09")
    assert [(i["day"], i["kind"], i["amount"]) for i in details["incomes"]] == [
        ("2026-09-15", "one_off", 2500),
        ("2026-09-05", "payment", 5000),
    ]
    assert [(c["client"]["id"], c["received"], c["sessions"]) for c in details["clients"]] == [
        (anna, 5000, 2),
        (boris, 2500, 1),
        (clara, 0, 2),
    ]

    forecast = await get(client, headers, "forecast")
    assert forecast["one_off"] == 2500
    assert forecast["one_off_count"] == 1
    assert [(d["client"]["id"], d["due"]) for d in forecast["dues"]] == [(anna, 5000)]
    assert [(r["client"]["id"], r["left"], r["price"]) for r in forecast["renewals"]] == [
        (clara, 1, 6000)
    ]
    assert forecast["total"] == 2500 + 5000 + 6000


async def test_finance_needs_trainer(client: AsyncClient, session: AsyncSession) -> None:
    _, trainer_id, _ = await setup_trainer(client)
    headers = await new_client(client, session, trainer_id, 501)
    response = await client.get("/api/trainer/finance/summary", headers=headers)
    assert response.status_code == 403
