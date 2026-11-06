"""Открытая регистрация: человек сам становится тренером кнопкой «Я тренер»."""

from collections.abc import Iterator

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_schedule_api import auth
from tests.test_trainers import make_user
from trenio.bot.handlers import SIGNUP_CALLBACK, start_text, webapp_keyboard
from trenio.config import get_settings
from trenio.services.trainers import (
    InviteError,
    InviteRejected,
    SignupClosed,
    get_active_trainer,
    set_trainer_active,
    sign_up,
)


@pytest.fixture
def signup_closed(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("TRAINER_SIGNUP_OPEN", "false")
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("TRAINER_SIGNUP_OPEN")
    get_settings.cache_clear()


async def test_sign_up_grants_access_with_trial(session: AsyncSession) -> None:
    user = await make_user(session, 7, "Анна")
    trainer = await sign_up(session, user, signup_open=True)
    assert trainer.user_id == user.id
    assert trainer.is_active
    assert trainer.referred_by_id is None
    assert trainer.trial_until is not None
    assert trainer.onboarded_at is None
    # Повторное нажатие ничего не меняет
    again = await sign_up(session, user, signup_open=True)
    assert again.id == trainer.id


async def test_sign_up_closed(session: AsyncSession) -> None:
    user = await make_user(session, 7, "Анна")
    with pytest.raises(SignupClosed):
        await sign_up(session, user, signup_open=False)
    assert await get_active_trainer(session, user.id) is None


async def test_disabled_trainer_cannot_sign_up_again(session: AsyncSession) -> None:
    user = await make_user(session, 7, "Анна")
    trainer = await sign_up(session, user, signup_open=True)
    await set_trainer_active(session, trainer.id, active=False)
    with pytest.raises(InviteRejected) as rejected:
        await sign_up(session, user, signup_open=True)
    assert rejected.value.reason == InviteError.DISABLED


async def test_api_become_trainer(client: AsyncClient) -> None:
    headers = await auth(client, 2002)
    me = (await client.get("/api/me", headers=headers)).json()
    assert me["trainer"] is None
    assert me["trainer_signup_open"] is True

    response = await client.post("/api/me/trainer", headers=headers)
    assert response.status_code == 200
    assert response.json()["onboarded_at"] is None

    me = (await client.get("/api/me", headers=headers)).json()
    assert me["is_trainer"] is True
    assert me["trainer"]["id"] == response.json()["id"]


@pytest.mark.usefixtures("signup_closed")
async def test_api_become_trainer_closed(client: AsyncClient) -> None:
    headers = await auth(client, 2002)
    assert (await client.get("/api/me", headers=headers)).json()["trainer_signup_open"] is False
    response = await client.post("/api/me/trainer", headers=headers)
    assert response.status_code == 403
    assert (await client.get("/api/me", headers=headers)).json()["trainer"] is None


def test_start_offers_signup() -> None:
    text = start_text("Иван", None, admin=False, signup_open=True)
    assert "«Я тренер»" in text
    assert "ссылку-приглашение" in text
    keyboard = webapp_keyboard("https://example.com", signup=True)
    assert keyboard is not None
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert [button.text for button in buttons] == ["Открыть Trenio", "Я тренер"]
    assert buttons[1].callback_data == SIGNUP_CALLBACK
    # Без https кнопки приложения нет, но «Я тренер» остаётся
    keyboard = webapp_keyboard("http://localhost", signup=True)
    assert keyboard is not None
    assert len(keyboard.inline_keyboard) == 1
    assert webapp_keyboard("http://localhost") is None
