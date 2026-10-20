"""Обращения тренеров: форма в Mini App, уведомление админу и ответ из админки в бот."""

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_admin import get
from tests.test_bookings import setup_trainer
from tests.test_schedule_api import second_trainer
from trenio.api.routes import admin as admin_route
from trenio.api.routes import trainer as trainer_route
from trenio.db.models import AdminAuditEntry
from trenio.services import support

Sent = list[tuple[int, str]]


@pytest.fixture
def alerts(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    sent: list[str] = []

    async def fake(text: str) -> None:
        sent.append(text)

    monkeypatch.setattr(trainer_route, "alert_admins", fake)
    return sent


@pytest.fixture
def answers(monkeypatch: pytest.MonkeyPatch) -> Sent:
    sent: Sent = []

    async def fake(telegram_id: int, text: str) -> None:
        sent.append((telegram_id, text))

    monkeypatch.setattr(admin_route, "send_answer", fake)
    return sent


async def test_trainer_sends_and_gets_answer(
    client: AsyncClient, session: AsyncSession, alerts: list[str], answers: Sent
) -> None:
    admin, _, _ = await setup_trainer(client)
    other = await second_trainer(client, session)

    response = await client.post(
        "/api/trainer/support",
        headers=other,
        json={"kind": "problem", "text": "  Не приходят напоминания  "},
    )
    assert response.status_code == 201, response.text
    ticket = response.json()
    assert (ticket["status"], ticket["text"], ticket["rating"]) == (
        "new",
        "Не приходят напоминания",
        None,
    )
    assert len(alerts) == 1 and "Проблема" in alerts[0] and "напоминания" in alerts[0]

    rows = await get(client, admin, "support")
    assert [(r["id"], r["status"], r["username"]) for r in rows] == [(ticket["id"], "new", "ivan")]
    assert rows[0]["trainer_name"]

    url = f"/api/admin/support/{ticket['id']}/answer"
    response = await client.post(url, headers=admin, json={"text": "Проверили, уже чиним"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "answered"
    assert answers[0][0] == 2002
    assert "«Не приходят напоминания»" in answers[0][1]
    assert answers[0][1].endswith("Проверили, уже чиним")

    # Тренер видит ответ в истории
    history = (await client.get("/api/trainer/support", headers=other)).json()
    assert history[0]["answer"] == "Проверили, уже чиним"
    assert history[0]["answered_at"] is not None

    entry = await session.scalar(
        select(AdminAuditEntry).where(AdminAuditEntry.action == "support.answered")
    )
    assert entry is not None and entry.target == f"support:{ticket['id']}"


async def test_review_needs_rating_and_close(
    client: AsyncClient, session: AsyncSession, alerts: list[str]
) -> None:
    admin, _, _ = await setup_trainer(client)
    other = await second_trainer(client, session)

    response = await client.post(
        "/api/trainer/support", headers=other, json={"kind": "review", "text": "Удобно"}
    )
    assert response.status_code == 422
    response = await client.post(
        "/api/trainer/support",
        headers=other,
        json={"kind": "review", "text": "Удобно", "rating": 5},
    )
    assert response.status_code == 201
    ticket_id = response.json()["id"]
    assert "★★★★★" in alerts[-1]
    # У вопроса оценки нет, даже если её прислали
    response = await client.post(
        "/api/trainer/support",
        headers=other,
        json={"kind": "idea", "text": "Тёмная тема", "rating": 3},
    )
    assert response.json()["rating"] is None

    url = f"/api/admin/support/{ticket_id}/status"
    response = await client.post(url, headers=admin, json={"closed": True})
    assert response.json()["status"] == "closed"
    assert [r["kind"] for r in await get(client, admin, "support?status=new")] == ["idea"]
    assert [r["id"] for r in await get(client, admin, "support?status=closed")] == [ticket_id]
    response = await client.post(url, headers=admin, json={"closed": False})
    assert response.json()["status"] == "new"


async def test_limits_and_blocked_bot(
    client: AsyncClient,
    session: AsyncSession,
    alerts: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin, _, _ = await setup_trainer(client)
    other = await second_trainer(client, session)
    monkeypatch.setattr(support, "DAILY_LIMIT", 2)
    for _ in range(2):
        response = await client.post(
            "/api/trainer/support", headers=other, json={"kind": "question", "text": "Как?"}
        )
        assert response.status_code == 201
    response = await client.post(
        "/api/trainer/support", headers=other, json={"kind": "question", "text": "Как?"}
    )
    assert response.status_code == 429

    async def blocked(telegram_id: int, text: str) -> None:
        raise TelegramForbiddenError(SendMessage(chat_id=telegram_id, text=text), "bot was blocked")

    monkeypatch.setattr(admin_route, "send_answer", blocked)
    ticket_id = (await get(client, admin, "support"))[0]["id"]
    response = await client.post(
        f"/api/admin/support/{ticket_id}/answer", headers=admin, json={"text": "Вот так"}
    )
    assert response.status_code == 502
    # Ответ не дошёл: обращение так и ждёт ответа
    assert (await get(client, admin, "support"))[0]["status"] == "new"

    # Не админ обращения не видит
    response = await client.get("/api/admin/support", headers=other)
    assert response.status_code == 403
