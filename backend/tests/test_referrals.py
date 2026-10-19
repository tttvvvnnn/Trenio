"""Личная ссылка тренера для коллег и учёт приглашённых."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_schedule_api import auth
from tests.test_trainers import make_invite, make_user
from trenio.db.models import Notification, Trainer
from trenio.delivery.texts import render
from trenio.services.trainers import (
    InviteError,
    InviteRejected,
    accept_invite,
    accept_referral,
    get_active_trainer,
    list_referrals,
    set_trainer_active,
)


async def make_trainer(session: AsyncSession, telegram_id: int, name: str) -> Trainer:
    user = await make_user(session, telegram_id, name)
    return await accept_invite(session, user, (await make_invite(session)).code)


async def test_referral_link_grants_access_and_remembers_inviter(session: AsyncSession) -> None:
    anna = await make_trainer(session, 7, "Анна")
    boris = await make_user(session, 8, "Борис")
    trainer = await accept_referral(session, boris, anna.referral_code)
    assert trainer.user_id == boris.id
    assert trainer.referred_by_id == anna.id
    assert trainer.referral_code != anna.referral_code

    # Ссылка многоразовая: по ней может прийти ещё один тренер
    vera = await make_user(session, 9, "Вера")
    await accept_referral(session, vera, anna.referral_code)
    assert [t.display_name for t in await list_referrals(session, anna)] == ["Вера", "Борис"]

    # Пригласившему пришло по уведомлению на каждого
    query = select(Notification).where(Notification.user_id == anna.user_id)
    rows = (await session.scalars(query.order_by(Notification.id))).all()
    assert len(rows) == 2
    message = await render(session, rows[0], rows[0].send_at)
    assert message is not None
    assert "пришёл тренер Борис" in message.text


async def test_existing_trainer_keeps_inviter(session: AsyncSession) -> None:
    anna = await make_trainer(session, 7, "Анна")
    boris = await make_trainer(session, 8, "Борис")
    # Уже тренер: ничего не меняется, пригласившим Анна не становится
    same = await accept_referral(session, await make_user(session, 8, "Борис"), anna.referral_code)
    assert same.id == boris.id
    assert same.referred_by_id is None
    # Своя ссылка тоже ничего не делает
    own = await accept_referral(session, await make_user(session, 7, "Анна"), anna.referral_code)
    assert own.referred_by_id is None
    assert await list_referrals(session, anna) == []


async def test_referral_rejections(session: AsyncSession) -> None:
    anna = await make_trainer(session, 7, "Анна")
    boris = await make_user(session, 8, "Борис")
    with pytest.raises(InviteRejected) as unknown:
        await accept_referral(session, boris, "nonexistent")
    assert unknown.value.reason is InviteError.NOT_FOUND

    # Отключённый тренер больше никого не приглашает
    await set_trainer_active(session, anna.id, False)
    with pytest.raises(InviteRejected) as disabled_inviter:
        await accept_referral(session, boris, anna.referral_code)
    assert disabled_inviter.value.reason is InviteError.NOT_FOUND
    assert await get_active_trainer(session, boris.id) is None

    # Отключённого админом чужая ссылка не возвращает
    await set_trainer_active(session, anna.id, True)
    vera = await make_trainer(session, 9, "Вера")
    await set_trainer_active(session, vera.id, False)
    with pytest.raises(InviteRejected) as disabled:
        await accept_referral(session, await make_user(session, 9, "Вера"), anna.referral_code)
    assert disabled.value.reason is InviteError.DISABLED


async def test_referrals_api(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from trenio.api.routes import trainer as routes

    async def username() -> str:
        return "trenio_test_bot"

    monkeypatch.setattr(routes, "get_bot_username", username)
    headers = await auth(client)
    response = await client.get("/api/trainer/referrals", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["url"].startswith("https://t.me/trenio_test_bot?start=r_")
    assert data["trainers"] == []

    admin = await session.scalar(select(Trainer))
    assert admin is not None
    await accept_referral(session, await make_user(session, 8, "Борис"), admin.referral_code)
    data = (await client.get("/api/trainer/referrals", headers=headers)).json()
    assert [t["display_name"] for t in data["trainers"]] == ["Борис"]
