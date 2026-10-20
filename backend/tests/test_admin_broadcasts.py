"""Рассылки тренерам: сегменты, тест себе, очередь и статистика доставки."""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_admin import get
from tests.test_bookings import setup_trainer
from tests.test_notifications import FakeChannel
from tests.test_schedule_api import second_trainer
from trenio.api.routes import admin as route
from trenio.db.models import Trainer, User
from trenio.db.session import get_sessionmaker
from trenio.delivery.sender import Sender


async def test_broadcast_flow(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, _, _ = await setup_trainer(client)
    await second_trainer(client, session)

    # Админ не в аудитории; второй тренер на пробном периоде
    audience = await get(client, headers, "broadcasts/audience?segment=all")
    assert audience["count"] == 1
    assert (await get(client, headers, "broadcasts/audience?segment=trial"))["count"] == 1
    assert (await get(client, headers, "broadcasts/audience?segment=pro"))["count"] == 0

    tested: list[tuple[int | None, str]] = []

    async def fake_test(user: User, text: str, with_button: bool) -> None:
        tested.append((user.telegram_id, text))

    monkeypatch.setattr(route, "send_test", fake_test)
    response = await client.post(
        "/api/admin/broadcasts/test", headers=headers, json={"text": "Новое в Trenio"}
    )
    assert response.status_code == 204
    assert tested and tested[0][1] == "Новое в Trenio"

    response = await client.post(
        "/api/admin/broadcasts", headers=headers, json={"text": "  ", "segment": "all"}
    )
    assert response.status_code == 422
    response = await client.post(
        "/api/admin/broadcasts", headers=headers, json={"text": "Привет", "segment": "pro"}
    )
    assert response.status_code == 409

    response = await client.post(
        "/api/admin/broadcasts",
        headers=headers,
        json={"text": "Новое в Trenio", "segment": "all", "with_button": False},
    )
    assert response.status_code == 201, response.text
    assert response.json()["recipients"] == 1

    channel = FakeChannel()
    assert await Sender(get_sessionmaker(), channel).run() == 1
    assert [text for _, text in channel.sent] == ["Новое в Trenio"]
    assert channel.messages[0].buttons == []

    history = await get(client, headers, "broadcasts")
    assert [(h["recipients"], h["sent"], h["pending"]) for h in history] == [(1, 1, 0)]


async def test_disabled_trainers_are_skipped(client: AsyncClient, session: AsyncSession) -> None:
    headers, _, _ = await setup_trainer(client)
    await second_trainer(client, session)
    await session.execute(update(Trainer).where(Trainer.id == 2).values(is_active=False))
    # Пробный период тут ни при чём: отключённым не пишем
    await session.execute(
        update(Trainer).where(Trainer.id == 2).values(trial_until=datetime.now(UTC))
    )
    await session.commit()
    assert (await get(client, headers, "broadcasts/audience?segment=all"))["count"] == 0
