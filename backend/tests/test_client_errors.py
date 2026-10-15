"""Ошибки Mini App: доходят до админов в Telegram и не заваливают их повторами."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from tests.conftest import ADMIN_TELEGRAM_ID
from tests.factories import make_init_data
from tests.test_api import login
from trenio.api.routes import client_errors as route
from trenio.services.client_errors import HOURLY_LIMIT, Limiter, error_text

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


def test_same_error_waits_ten_minutes() -> None:
    limiter = Limiter()
    assert limiter.allow("boom", NOW)
    assert not limiter.allow("boom", NOW + timedelta(minutes=9))
    assert limiter.allow("other", NOW + timedelta(minutes=9))
    assert limiter.allow("boom", NOW + timedelta(minutes=10))


def test_hourly_limit() -> None:
    limiter = Limiter()
    for index in range(HOURLY_LIMIT):
        assert limiter.allow(f"error {index}", NOW)
    assert not limiter.allow("one more", NOW + timedelta(minutes=30))
    assert limiter.allow("one more", NOW + timedelta(hours=1))


def test_text_has_no_names() -> None:
    text = error_text(
        message="TypeError: x is undefined",
        stack="TypeError: x is undefined\n at a\n at b",
        screen="at ClientCard",
        user_id=7,
        role="тренер",
        version="0.10.0",
        env="prod",
    )
    assert "Пользователь #7, тренер" in text
    assert "Где: at ClientCard" in text
    assert "TypeError: x is undefined" in text


async def test_report_goes_to_admins(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[frozenset[int], str]] = []

    async def fake(admin_ids: frozenset[int], text: str) -> None:
        sent.append((admin_ids, text))

    monkeypatch.setattr(route, "send_to_admins", fake)
    monkeypatch.setattr(route.client_errors, "limiter", Limiter())
    token = await login(client, make_init_data(user_id=4201, first_name="Оля"))
    headers = {"Authorization": f"Bearer {token}"}

    body = {"message": "TypeError: boom", "screen": "at Calendar"}
    response = await client.post("/api/client-errors", json=body, headers=headers)
    assert response.status_code == 204, response.text
    # Повтор склеивается
    response = await client.post("/api/client-errors", json=body, headers=headers)
    assert response.status_code == 204

    assert len(sent) == 1
    admin_ids, text = sent[0]
    assert admin_ids == frozenset({ADMIN_TELEGRAM_ID})
    assert "клиент" in text and "TypeError: boom" in text and "Оля" not in text


async def test_report_needs_login(client: AsyncClient) -> None:
    response = await client.post("/api/client-errors", json={"message": "boom"})
    assert response.status_code == 401
