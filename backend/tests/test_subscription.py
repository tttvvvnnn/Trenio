"""Подписка тренера: пробный период, бесплатный лимит клиентов и предупреждения."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_bookings import new_client, trainer_row
from tests.test_schedule_api import auth, second_trainer
from trenio.db.models import Notification, Trainer
from trenio.delivery.texts import render
from trenio.services import subscription
from trenio.services.subscription import ClientLimitReached, State


async def other_trainer(client: AsyncClient, session: AsyncSession) -> tuple[dict[str, str], int]:
    headers = await second_trainer(client, session)
    me = (await client.get("/api/me", headers=headers)).json()
    return headers, me["trainer"]["id"]


async def end_trial(session: AsyncSession, trainer_id: int) -> Trainer:
    trainer = await trainer_row(session, trainer_id)
    trainer.trial_until = datetime.now(UTC) - timedelta(minutes=1)
    await session.commit()
    return trainer


async def get_sub(client: AsyncClient, headers: dict[str, str]) -> dict[str, object]:
    response = await client.get("/api/trainer/subscription", headers=headers)
    assert response.status_code == 200, response.text
    data: dict[str, object] = response.json()
    return data


async def test_new_trainer_gets_trial(client: AsyncClient, session: AsyncSession) -> None:
    headers, trainer_id = await other_trainer(client, session)
    sub = await get_sub(client, headers)
    assert sub["state"] == "trial"
    assert sub["client_limit"] is None
    trainer = await trainer_row(session, trainer_id)
    assert trainer.trial_until is not None
    left = trainer.trial_until - datetime.now(UTC)
    assert timedelta(days=29) < left <= timedelta(days=30)
    assert sub["plans"] == [
        {"key": "month", "days": 30, "price": 349, "balance_used": 0, "amount": 349},
    ]
    # Админ всегда на Pro
    assert (await get_sub(client, await auth(client)))["state"] == "admin"


async def test_free_plan_limits_new_clients(client: AsyncClient, session: AsyncSession) -> None:
    headers, trainer_id = await other_trainer(client, session)
    # В пробный период клиентов сколько угодно
    for telegram_id in (501, 502, 503, 504):
        await new_client(client, session, trainer_id, telegram_id)
    await end_trial(session, trainer_id)

    sub = await get_sub(client, headers)
    assert sub["state"] == "free"
    assert (sub["clients"], sub["client_limit"], sub["can_add_client"]) == (4, 3, False)

    # Новый клиент по ссылке не проходит, тренеру уходит уведомление
    with pytest.raises(ClientLimitReached):
        await new_client(client, session, trainer_id, 505)
    trainer = await trainer_row(session, trainer_id)
    rows = (
        await session.scalars(select(Notification).where(Notification.user_id == trainer.user_id))
    ).all()
    limit_rows = [row for row in rows if row.kind == "client_limit"]
    assert len(limit_rows) == 1
    message = await render(session, limit_rows[0], datetime.now(UTC))
    assert message is not None and "бесплатном тарифе" in message.text

    # Уже добавленный клиент повторно открывает ссылку без ошибки
    await new_client(client, session, trainer_id, 501)

    # Клиента без Telegram тоже не добавить
    response = await client.post(
        "/api/trainer/clients", headers=headers, json={"first_name": "Олег", "last_name": None}
    )
    assert response.status_code == 402
    assert "бесплатном тарифе" in response.json()["detail"]

    # С Pro ограничение снимается
    trainer = await trainer_row(session, trainer_id)
    subscription.extend_pro(trainer, 30, datetime.now(UTC))
    await session.commit()
    assert (await get_sub(client, headers))["state"] == "pro"
    await new_client(client, session, trainer_id, 505)


async def test_free_plan_allows_three_clients(client: AsyncClient, session: AsyncSession) -> None:
    headers, trainer_id = await other_trainer(client, session)
    await end_trial(session, trainer_id)
    for telegram_id in (501, 502):
        await new_client(client, session, trainer_id, telegram_id)
    response = await client.post(
        "/api/trainer/clients", headers=headers, json={"first_name": "Олег", "last_name": None}
    )
    assert response.status_code == 201
    assert (await get_sub(client, headers))["can_add_client"] is False


async def test_extend_pro_adds_after_trial(session: AsyncSession) -> None:
    now = datetime(2030, 1, 1, tzinfo=UTC)
    trainer = Trainer(trial_until=now + timedelta(days=10), pro_until=None)
    assert subscription.extend_pro(trainer, 30, now) == now + timedelta(days=40)
    # Pro давно кончился: считаем от сегодня
    trainer = Trainer(trial_until=now - timedelta(days=50), pro_until=now - timedelta(days=5))
    assert subscription.extend_pro(trainer, 365, now) == now + timedelta(days=365)


async def test_ending_alerts(client: AsyncClient, session: AsyncSession) -> None:
    _, trainer_id = await other_trainer(client, session)
    trainer = await trainer_row(session, trainer_id)
    now = datetime.now(UTC)
    trainer.trial_until = now + timedelta(days=2)
    await session.commit()

    await subscription.schedule_ending_alerts(session, now)
    await subscription.schedule_ending_alerts(session, now)
    query = select(Notification).where(Notification.kind == "subscription_ending")
    rows = (await session.scalars(query.order_by(Notification.send_at))).all()
    # До конца меньше трёх дней: предупреждение уходит сразу, второе — в момент конца
    assert [row.payload["days"] for row in rows] == [3, 0]
    soon = await render(session, rows[0], now)
    assert soon is not None
    assert soon.text.startswith("⏳ Пробный период Trenio закончится через 2 дня")
    assert await render(session, rows[1], now) is not None

    # Оплатил: старые предупреждения больше не нужны
    subscription.extend_pro(trainer, 30, now)
    await session.commit()
    assert await render(session, rows[0], now) is None

    # Админу не пишем
    admin = await session.scalar(select(Trainer).where(Trainer.id != trainer_id))
    assert admin is not None and subscription.state_of(admin, now) is State.ADMIN
