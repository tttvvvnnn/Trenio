"""Предупреждения о конце срока блока, в котором ещё остались занятия."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_bookings import me_id, new_client, setup_trainer
from tests.test_notifications import FakeChannel, dispatch
from tests.test_packages import sell
from trenio.db.models import Notification
from trenio.services.packages import schedule_expiry_alerts

# Москва: 10:00 по времени тренера — это 07:00 UTC
NOW = datetime(2030, 3, 1, 5, tzinfo=UTC)


async def expiry_rows(session: AsyncSession) -> list[tuple[str, int, datetime, str]]:
    rows = await session.scalars(
        select(Notification)
        .where(Notification.kind == "package_expiring")
        .order_by(Notification.send_at, Notification.id)
        .execution_options(populate_existing=True)
    )
    return [(r.payload["role"], r.payload["days"], r.send_at, r.status) for r in rows]


async def test_alerts_week_and_day_before(client: AsyncClient, session: AsyncSession) -> None:
    headers, trainer_id, _ = await setup_trainer(client)
    client_headers = await new_client(client, session, trainer_id, 3003)
    client_id = await me_id(client, client_headers)
    await sell(client, headers, client_id, purchased_on="2030-02-01", valid_until="2030-03-08")

    await schedule_expiry_alerts(session, NOW)
    await schedule_expiry_alerts(session, NOW)  # повтор ничего не добавляет
    week = datetime(2030, 3, 1, 7, tzinfo=UTC)
    day = datetime(2030, 3, 7, 7, tzinfo=UTC)
    assert await expiry_rows(session) == [
        ("client", 7, week, "pending"),
        ("trainer", 7, week, "pending"),
        ("client", 1, day, "pending"),
        ("trainer", 1, day, "pending"),
    ]

    channel = FakeChannel()
    await dispatch(channel, week)
    texts = dict(channel.sent)
    assert "кончается через 7 дней, 8 мар" in texts[3003]
    assert "ещё 10 занятий" in texts[3003]
    assert "Осталось доплатить 20" in texts[3003]
    assert "У клиента" in texts[1001]


async def test_extended_block_drops_old_alert(client: AsyncClient, session: AsyncSession) -> None:
    headers, trainer_id, _ = await setup_trainer(client)
    client_headers = await new_client(client, session, trainer_id, 3003)
    client_id = await me_id(client, client_headers)
    package = await sell(
        client, headers, client_id, purchased_on="2030-02-01", valid_until="2030-03-08"
    )
    await schedule_expiry_alerts(session, NOW)

    response = await client.patch(
        f"/api/trainer/packages/{package['id']}",
        headers=headers,
        json={"valid_until": "2030-04-30"},
    )
    assert response.status_code == 200, response.text
    channel = FakeChannel()
    await dispatch(channel, NOW + timedelta(days=7))
    assert channel.sent == []
    assert {status for *_, status in await expiry_rows(session)} == {"skipped"}


async def test_no_alert_when_block_is_used_up(client: AsyncClient, session: AsyncSession) -> None:
    headers, trainer_id, _ = await setup_trainer(client)
    client_headers = await new_client(client, session, trainer_id, 3003)
    client_id = await me_id(client, client_headers)
    await sell(
        client,
        headers,
        client_id,
        sessions_count=1,
        purchased_on="2030-02-01",
        valid_until="2030-03-08",
    )
    package = (await client.get("/api/client/packages", headers=client_headers)).json()[0]
    response = await client.post(
        f"/api/trainer/packages/{package['id']}/sessions",
        headers=headers,
        json={"day": "2030-02-10"},
    )
    assert response.status_code in (200, 201), response.text
    await schedule_expiry_alerts(session, NOW)
    assert await expiry_rows(session) == []
