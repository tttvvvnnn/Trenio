"""Статистика тренера за месяц."""

from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_bookings import me_id, new_client, setup_trainer
from tests.test_finance import booking_at
from tests.test_packages import mark
from trenio.db.models import Booking


def msk(day: str, hour: int = 10) -> datetime:
    # 10:00 по Москве — 07:00 UTC
    return datetime.fromisoformat(f"{day}T{hour - 3:02d}:00:00+00:00").astimezone(UTC)


async def test_month_stats(client: AsyncClient, session: AsyncSession) -> None:
    headers, trainer_id, service_id = await setup_trainer(client)
    anna = await me_id(client, await new_client(client, session, trainer_id, 3003))
    oleg = await me_id(client, await new_client(client, session, trainer_id, 3004))

    # Сентябрь 2026: у Анны три понедельника и отмена, у Олега одно занятие во вторник
    for day, attendance in (
        ("2026-09-07", "attended"),
        ("2026-09-14", "attended"),
        ("2026-09-21", "missed_charged"),
    ):
        booking_id = await booking_at(session, trainer_id, anna, service_id, msk(day))
        status_code, _ = await mark(client, headers, booking_id, attendance)
        assert status_code == 200
    cancelled = await booking_at(session, trainer_id, anna, service_id, msk("2026-09-28"))
    booking = await session.get(Booking, cancelled)
    assert booking is not None
    booking.status, booking.cancelled_by = "cancelled", "client"
    await session.commit()
    tuesday = await booking_at(session, trainer_id, oleg, service_id, msk("2026-09-01"))
    await mark(client, headers, tuesday, "attended")
    # Анна записана на будущее, поэтому не «пропала»
    await booking_at(session, trainer_id, anna, service_id, msk("2030-01-07"))

    response = await client.get("/api/trainer/stats?month=2026-09", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["visits"] == {
        "attended": 3,
        "missed_charged": 1,
        "missed_free": 0,
        "unmarked": 0,
        "upcoming": 0,
        "cancelled_by_client": 1,
        "cancelled_by_trainer": 0,
    }
    monday, tuesday_load = data["load"][0], data["load"][1]
    # Четыре понедельника по 2 часа, заняты три часа; отменённая запись не считается
    assert (monday["open_minutes"], monday["booked_minutes"]) == (480, 180)
    assert (tuesday_load["open_minutes"], tuesday_load["booked_minutes"]) == (0, 60)
    assert [(t["client"]["id"], t["sessions"]) for t in data["top"]] == [(anna, 2), (oleg, 1)]
    assert [x["client"]["id"] for x in data["lapsed"]] == [oleg]
