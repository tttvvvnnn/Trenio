"""Вход в веб-админку: виджет Telegram, подтверждение в боте, кука, CSRF и журнал."""

import time
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import ADMIN_TELEGRAM_ID
from tests.factories import BOT_TOKEN, make_init_data, make_login_widget
from tests.test_api import login as app_login
from trenio.api.routes import admin_auth as route
from trenio.auth.telegram import InitDataError, validate_login_widget
from trenio.db.models import AdminAuditEntry, AdminSession, User
from trenio.services import admin_auth
from trenio.services.admin_auth import LoginLimiter

CONFIRM = timedelta(minutes=10)


@pytest.fixture(autouse=True)
def sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, str]]:
    """Подтверждения, которые «ушли» в бот: настоящий Telegram в тестах недоступен."""
    messages: list[tuple[int, str]] = []

    async def fake(_: Any, telegram_id: int, admin_session: AdminSession) -> None:
        messages.append((telegram_id, admin_session.id))

    monkeypatch.setattr(route, "send_login_confirmation", fake)
    monkeypatch.setattr(route, "limiter", LoginLimiter())
    return messages


def test_widget_signature() -> None:
    data = {key: str(value) for key, value in make_login_widget(7, "Анна").items()}
    user = validate_login_widget(data, BOT_TOKEN, max_age=60)
    assert (user.id, user.first_name, user.username) == (7, "Анна", "ivan")

    with pytest.raises(InitDataError):
        validate_login_widget({**data, "first_name": "Борис"}, BOT_TOKEN, max_age=60)
    with pytest.raises(InitDataError):
        validate_login_widget(data, BOT_TOKEN + "x", max_age=60)
    old = make_login_widget(7, auth_date=int(time.time()) - 600)
    with pytest.raises(InitDataError):
        validate_login_widget({k: str(v) for k, v in old.items()}, BOT_TOKEN, max_age=60)


def test_login_limiter() -> None:
    now = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
    limiter = LoginLimiter(attempts=2, window=timedelta(minutes=10))
    assert limiter.allow("1.2.3.4", now)
    assert limiter.allow("1.2.3.4", now)
    assert not limiter.allow("1.2.3.4", now + timedelta(minutes=5))
    assert limiter.allow("5.6.7.8", now)
    assert limiter.allow("1.2.3.4", now + timedelta(minutes=10))


async def _confirm(session: AsyncSession, session_id: str, approve: bool = True) -> None:
    admin_session = await session.get(AdminSession, session_id)
    assert admin_session is not None
    owner = await session.get(User, admin_session.user_id)
    assert owner is not None
    answered = await admin_auth.answer_confirmation(
        session, session_id, owner, approve, datetime.now(UTC), CONFIRM
    )
    assert answered is not None
    await session.commit()


async def _actions(session: AsyncSession) -> list[str]:
    rows = await session.scalars(select(AdminAuditEntry).order_by(AdminAuditEntry.id))
    return [row.action for row in rows]


async def test_login_needs_confirmation_in_bot(
    client: AsyncClient, session: AsyncSession, sent: list[tuple[int, str]]
) -> None:
    response = await client.post(
        "/api/admin/auth/telegram", json=make_login_widget(ADMIN_TELEGRAM_ID, "Тихон")
    )
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "pending"
    assert response.json()["csrf_token"] is None
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/api" in cookie
    assert len(sent) == 1 and sent[0][0] == ADMIN_TELEGRAM_ID

    # Пока админ не нажал «Да», в админку не пускает
    assert (await client.get("/api/admin/overview")).status_code == 401
    assert (await client.get("/api/admin/auth/session")).json()["state"] == "pending"

    await _confirm(session, sent[0][1])
    state = (await client.get("/api/admin/auth/session")).json()
    assert state["state"] == "active" and state["name"] == "Тихон"
    assert (await client.get("/api/admin/overview")).status_code == 200

    # Изменяющий запрос без CSRF-токена не проходит, с ним — проходит
    listed = (await client.get("/api/admin/auth/sessions")).json()
    assert [row["current"] for row in listed] == [True]
    revoke_url = f"/api/admin/auth/sessions/{listed[0]['id']}/revoke"
    assert (await client.post(revoke_url)).status_code == 403
    response = await client.post(revoke_url, headers={"X-CSRF-Token": state["csrf_token"]})
    assert response.status_code == 204
    assert (await client.get("/api/admin/overview")).status_code == 401
    assert (await client.get("/api/admin/auth/session")).json()["state"] == "expired"
    assert await _actions(session) == ["login.requested", "login.confirmed", "session.revoked"]


async def test_denied_login(
    client: AsyncClient, session: AsyncSession, sent: list[tuple[int, str]]
) -> None:
    await client.post("/api/admin/auth/telegram", json=make_login_widget(ADMIN_TELEGRAM_ID))
    await _confirm(session, sent[0][1], approve=False)
    assert (await client.get("/api/admin/auth/session")).json()["state"] == "denied"
    assert (await client.get("/api/admin/overview")).status_code == 401
    # Второй раз на ту же кнопку ответить нельзя
    admin_session = await session.get(AdminSession, sent[0][1], populate_existing=True)
    assert admin_session is not None
    owner = await session.get(User, admin_session.user_id)
    assert owner is not None
    assert (
        await admin_auth.answer_confirmation(
            session, admin_session.id, owner, True, datetime.now(UTC), CONFIRM
        )
        is None
    )


async def test_unconfirmed_login_expires() -> None:
    now = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
    admin_session = AdminSession(
        id="x",
        user_id=1,
        csrf_token="y",
        status="pending",
        created_at=now,
        expires_at=now + timedelta(hours=12),
    )
    assert admin_auth.state(admin_session, now + timedelta(minutes=9), CONFIRM).value == "pending"
    assert admin_auth.state(admin_session, now + timedelta(minutes=11), CONFIRM).value == "expired"


async def test_not_admin_is_rejected(
    client: AsyncClient, session: AsyncSession, sent: list[tuple[int, str]]
) -> None:
    response = await client.post("/api/admin/auth/telegram", json=make_login_widget(7))
    assert response.status_code == 403
    assert sent == []
    assert await _actions(session) == ["login.rejected"]


async def test_forged_widget_is_rejected(client: AsyncClient) -> None:
    data = make_login_widget(ADMIN_TELEGRAM_ID)
    data["first_name"] = "Взломщик"
    assert (await client.post("/api/admin/auth/telegram", json=data)).status_code == 401


async def test_app_token_is_not_an_admin_cookie(client: AsyncClient) -> None:
    token = await app_login(client, make_init_data(user_id=ADMIN_TELEGRAM_ID))
    # Токен Mini App в заголовке открывает админку Mini App, как раньше
    headers = {"Authorization": f"Bearer {token}"}
    assert (await client.get("/api/admin/overview", headers=headers)).status_code == 200
    # Но вместо куки веб-админки не годится
    client.cookies.set(route.COOKIE, token, path="/api")
    assert (await client.get("/api/admin/overview")).status_code == 401


async def test_audit_log_is_append_only(session: AsyncSession) -> None:
    await admin_auth.audit(session, None, "test.entry")
    await session.commit()
    with pytest.raises(DBAPIError, match="append-only"):
        await session.execute(text("UPDATE admin_audit_log SET action = 'changed'"))
    await session.rollback()
    with pytest.raises(DBAPIError, match="append-only"):
        await session.execute(text("DELETE FROM admin_audit_log"))
    await session.rollback()
