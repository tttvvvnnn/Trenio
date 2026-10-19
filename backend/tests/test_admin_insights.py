"""Главный экран админки: рост, кому нужна помощь, лента, удержание, состояние."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_admin import get
from tests.test_bookings import new_client, setup_trainer
from tests.test_finance import booking_at
from tests.test_packages import client_id_of
from tests.test_schedule_api import create_service, second_trainer
from trenio.api.routes import client_errors as error_route
from trenio.db.models import Trainer
from trenio.services import client_errors
from trenio.services.admin_insights import COHORT_WEEKS, SERIES
from trenio.services.client_errors import Limiter


async def test_insights(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, trainer_id, service_id = await setup_trainer(client, price=2500)
    other = await second_trainer(client, session)
    anna = await client_id_of(client, await new_client(client, session, trainer_id, 501))
    now = datetime.now(UTC).replace(microsecond=0)
    # Вчера клиент сам записался и занятие прошло, 10 дней назад — ещё одно
    await booking_at(session, trainer_id, anna, service_id, now - timedelta(days=1))
    await booking_at(session, trainer_id, anna, service_id, now - timedelta(days=10))
    # Второй тренер пришёл три дня назад и так и не настроился
    other_id = (await client.get("/api/me", headers=other)).json()["trainer"]["id"]
    await session.execute(
        update(Trainer)
        .where(Trainer.id == other_id)
        .values(created_at=now - timedelta(days=3, hours=1))
    )
    await session.commit()

    async def silent(admin_ids: frozenset[int], text: str) -> None:
        pass

    monkeypatch.setattr(error_route, "send_to_admins", silent)
    monkeypatch.setattr(client_errors, "limiter", Limiter())
    for _ in range(2):
        response = await client.post(
            "/api/client-errors",
            headers=other,
            json={"message": "TypeError: boom", "screen": "at Calendar"},
        )
        assert response.status_code == 204

    data = await get(client, headers, "insights")
    pulse = data["pulse"]
    assert len(pulse["live_trainers"]) == SERIES
    assert pulse["live_trainers"][-1] == 1
    assert pulse["sessions"][-2:] == [1, 1]
    # Обе записи созданы сейчас, обе — клиентом
    assert pulse["self_booked"][-1] == 100
    assert pulse["self_booked"][0] is None

    # Админа в списке нет, второй тренер застрял на настройке
    assert data["attention"] == [{"trainer_id": other_id, "reason": "not_set_up", "count": 3}]

    texts = [event["text"] for event in data["feed"]]
    assert any(t.endswith("новый тренер, пригласил(а) Иван") for t in texts), texts
    assert any(t.endswith(": первый клиент") for t in texts)
    assert any(t.endswith(": клиент впервые записался сам") for t in texts)
    assert "Ошибка: TypeError: boom · at Calendar · 2 раза" in texts
    assert data["feed"] == sorted(data["feed"], key=lambda e: e["at"], reverse=True)

    assert len(data["cohorts"]) == COHORT_WEEKS
    assert data["cohort_points"] == [1, 2, 4]
    # Админ в удержании не считается, второй тренер пришёл на этой или прошлой неделе
    assert sum(c["trainers"] for c in data["cohorts"]) == 1
    assert data["cohorts"][-1]["alive"] == [None, None, None]

    assert data["usage"]["base"] == 1
    assert data["usage"]["features"]["self_booking"] == 1
    assert data["usage"]["features"]["packages"] == 0
    assert data["health"]["errors_day"] == 2

    trainers = await get(client, headers, "trainers")
    journey = next(t for t in trainers if t["id"] == trainer_id)["journey"]
    assert journey["first_client_at"] is not None
    assert journey["first_client_booking_at"] is not None
    assert journey["first_package_at"] is None


async def test_quiet_and_unmarked(client: AsyncClient, session: AsyncSession) -> None:
    headers, trainer_id, service_id = await setup_trainer(client)
    other = await second_trainer(client, session)
    other_id = (await client.get("/api/me", headers=other)).json()["trainer"]["id"]
    # Второй тренер настроен: профиль, услуга и часы
    response = await client.patch("/api/trainer/me", headers=other, json={"display_name": "Игорь"})
    assert response.status_code == 200
    other_service = await create_service(client, other)
    response = await client.post(
        "/api/trainer/schedule/rules",
        headers=other,
        json={"weekday": 0, "start": "10:00", "end": "12:00"},
    )
    assert response.status_code == 201
    anna = await client_id_of(client, await new_client(client, session, other_id, 501))
    now = datetime.now(UTC).replace(microsecond=0)

    # Последнее занятие 9 дней назад — затих
    await booking_at(session, other_id, anna, other_service, now - timedelta(days=9))
    data = await get(client, headers, "insights")
    assert data["attention"] == [{"trainer_id": other_id, "reason": "quiet", "count": 9}]
    assert any(e["kind"] == "quiet" for e in data["feed"])

    # Пять вчерашних занятий без отметки — уже не затих, но не отмечает
    for hours in range(5):
        await booking_at(
            session, other_id, anna, other_service, now - timedelta(days=1, hours=hours * 2)
        )
    data = await get(client, headers, "insights")
    assert data["attention"] == [{"trainer_id": other_id, "reason": "unmarked", "count": 6}]


async def test_insights_admin_only(client: AsyncClient, session: AsyncSession) -> None:
    other = await second_trainer(client, session)
    assert (await client.get("/api/admin/insights", headers=other)).status_code == 403


def test_plural() -> None:
    from trenio.services.admin_digest import plural

    assert plural(1, "день", "дня", "дней") == "1 день"
    assert plural(3, "день", "дня", "дней") == "3 дня"
    assert plural(11, "день", "дня", "дней") == "11 дней"
    assert plural(22, "день", "дня", "дней") == "22 дня"


async def test_digest(client: AsyncClient, session: AsyncSession) -> None:
    from trenio.services.admin_digest import digest_text

    _, trainer_id, service_id = await setup_trainer(client)
    other = await second_trainer(client, session)
    other_id = (await client.get("/api/me", headers=other)).json()["trainer"]["id"]
    anna = await client_id_of(client, await new_client(client, session, trainer_id, 501))
    now = datetime.now(UTC).replace(microsecond=0)
    await booking_at(session, trainer_id, anna, service_id, now - timedelta(days=1))
    await session.execute(
        update(Trainer).where(Trainer.id == other_id).values(created_at=now - timedelta(days=5))
    )
    await session.commit()

    text = await digest_text(session, datetime.now(UTC), frozenset({1001}))
    assert "Живые тренеры: 1 (+1 к прошлой неделе)" in text
    assert "Занятий: 1 (+1 к прошлой неделе)" in text
    assert "Записались сами: 100%" in text
    assert "• Иван @ivan: не настроил услуги и часы, 5 дней" in text
