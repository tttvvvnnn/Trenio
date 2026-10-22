"""Действия админа с тренером: Pro в подарок, сообщение в бот, удаление."""

from datetime import UTC, datetime, timedelta

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_admin import get
from tests.test_bookings import new_client, setup_trainer
from tests.test_packages import client_id_of
from tests.test_schedule_api import Headers, second_trainer
from trenio.api.routes import admin as route
from trenio.db.models import (
    AdminAuditEntry,
    SubscriptionPayment,
    SupportTicket,
    Trainer,
    User,
)


async def _other(client: AsyncClient, session: AsyncSession) -> tuple[Headers, int]:
    headers = await second_trainer(client, session)
    trainer_id: int = (await client.get("/api/me", headers=headers)).json()["trainer"]["id"]
    return headers, trainer_id


async def _actions(session: AsyncSession) -> list[str]:
    rows = await session.scalars(select(AdminAuditEntry.action).order_by(AdminAuditEntry.id))
    return list(rows)


async def test_extend_pro(client: AsyncClient, session: AsyncSession) -> None:
    headers, _, _ = await setup_trainer(client)
    _, other_id = await _other(client, session)
    trainer = await session.get(Trainer, other_id)
    assert trainer is not None and trainer.trial_until is not None
    trial_end = trainer.trial_until

    response = await client.post(
        f"/api/admin/trainers/{other_id}/pro", headers=headers, json={"days": 30}
    )
    assert response.status_code == 200, response.text
    # Подарок идёт после пробного периода, а не вместо него
    until = datetime.fromisoformat(response.json()["pro_until"])
    assert abs(until - (trial_end + timedelta(days=30))) < timedelta(seconds=1)
    response = await client.post(
        f"/api/admin/trainers/{other_id}/pro", headers=headers, json={"days": 0}
    )
    assert response.status_code == 422
    assert await _actions(session) == ["trainer.pro_extended"]


async def test_message(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, _, _ = await setup_trainer(client)
    _, other_id = await _other(client, session)
    sent: list[tuple[int, str]] = []

    async def fake(telegram_id: int, text: str) -> None:
        sent.append((telegram_id, text))

    monkeypatch.setattr(route, "send_to_trainer", fake)
    url = f"/api/admin/trainers/{other_id}/message"
    response = await client.post(url, headers=headers, json={"text": "  Привет!  "})
    assert response.status_code == 204, response.text
    assert sent == [(2002, "Привет!")]

    async def blocked(telegram_id: int, text: str) -> None:
        raise TelegramForbiddenError(SendMessage(chat_id=telegram_id, text=text), "bot was blocked")

    monkeypatch.setattr(route, "send_to_trainer", blocked)
    response = await client.post(url, headers=headers, json={"text": "Ещё"})
    assert response.status_code == 502
    assert "blocked" in response.json()["detail"]
    # В журнале только доставленное
    assert await _actions(session) == ["trainer.messaged"]


async def test_delete_trainer(client: AsyncClient, session: AsyncSession) -> None:
    headers, admin_trainer_id, _ = await setup_trainer(client)
    other_headers, other_id = await _other(client, session)
    other_user = await client_id_of(client, other_headers)
    # У второго тренера есть клиент; клиент остаётся, пропадает только связь
    trainer = await session.get(Trainer, other_id)
    assert trainer is not None
    name = trainer.display_name
    await new_client(client, session, other_id, 601)

    url = f"/api/admin/trainers/{other_id}/delete"
    response = await client.post(
        url, headers=headers, json={"confirm_name": "не то", "reason": "x"}
    )
    assert response.status_code == 422
    response = await client.post(
        url, headers=headers, json={"confirm_name": name.upper(), "reason": "попросил сам"}
    )
    assert response.status_code == 204, response.text

    session.expire_all()
    assert await session.get(Trainer, other_id) is None
    assert await session.get(User, other_user) is None
    assert await session.scalar(select(User.id).where(User.telegram_id == 601)) is not None
    entry = await session.scalar(
        select(AdminAuditEntry).where(AdminAuditEntry.action == "trainer.deleted")
    )
    assert entry is not None and entry.payload["clients"] == 1

    response = await client.post(
        f"/api/admin/trainers/{admin_trainer_id}/delete",
        headers=headers,
        json={"confirm_name": "Иван", "reason": "x"},
    )
    assert response.status_code == 409


async def test_profile(client: AsyncClient, session: AsyncSession) -> None:
    headers, trainer_id, _ = await setup_trainer(client)
    _, other_id = await _other(client, session)
    await client.post(f"/api/admin/trainers/{other_id}/pro", headers=headers, json={"days": 30})
    session.add_all(
        [
            SubscriptionPayment(
                trainer_id=other_id,
                plan="month",
                days=30,
                price=990,
                amount=890,
                balance_used=100,
                status="paid",
                paid_at=datetime.now(UTC),
            ),
            SubscriptionPayment(trainer_id=other_id, plan="month", days=30, price=990, amount=990),
            SupportTicket(trainer_id=other_id, kind="idea", text="Тёмная тема"),
        ]
    )
    await session.commit()

    response = await client.get(f"/api/admin/trainers/{other_id}", headers=headers)
    assert response.status_code == 200, response.text
    profile = response.json()
    assert profile["trainer"]["id"] == other_id and profile["telegram_id"] == 2002
    assert len(profile["activity"]) == 30
    # Учитываются только оплаченные, но в списке видны все
    assert profile["paid_total"] == 990
    assert [p["status"] for p in profile["payments"]] == ["pending", "paid"]
    assert [t["text"] for t in profile["tickets"]] == ["Тёмная тема"]
    assert [a["action"] for a in profile["audit"]] == ["trainer.pro_extended"]
    assert profile["services"] == [] and profile["hours"] == []
    # История: свежие сверху, оплата и обращение рядом с получением доступа
    kinds = [e["kind"] for e in profile["events"]]
    assert kinds[-1] == "joined" and {"paid", "ticket"} <= set(kinds)
    assert profile["trainer"]["paid_total"] == 990
    listed = {t["id"]: t["paid_total"] for t in await get(client, headers, "trainers")}
    assert listed == {trainer_id: 0, other_id: 990}

    own = (await client.get(f"/api/admin/trainers/{trainer_id}", headers=headers)).json()
    assert [s["is_active"] for s in own["services"]] == [True]
    assert own["hours"] == [{"weekday": 0, "start": "10:00", "end": "12:00"}]

    response = await client.get("/api/admin/trainers/999999", headers=headers)
    assert response.status_code == 404
