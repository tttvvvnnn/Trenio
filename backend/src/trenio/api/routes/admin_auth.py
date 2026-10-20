"""Вход в веб-админку: Telegram Login Widget, подтверждение в боте, кука и CSRF.

Mini App ходит в API с токеном в заголовке, веб-админка — с httpOnly-кукой. Скрипт на
странице куку не прочитает, а чужой сайт не отправит её из-за SameSite=Strict. Запросы,
которые что-то меняют, дополнительно несут X-CSRF-Token.
"""

import hmac
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from trenio.api.deps import SessionDep, SettingsDep
from trenio.auth.telegram import InitDataError, validate_login_widget
from trenio.auth.tokens import Audience, TokenError, create_access_token, decode_admin_token
from trenio.bot.admin import send_login_confirmation
from trenio.bot.setup import get_bot, get_bot_username
from trenio.config import Settings
from trenio.db.models import AdminSession, User
from trenio.services import admin_auth
from trenio.services.admin_auth import LoginLimiter, SessionState
from trenio.services.users import get_user, upsert_telegram_user

logger = logging.getLogger(__name__)

COOKIE = "trenio_admin"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# last_seen_at обновляем не чаще раза в минуту, чтобы каждый запрос не писал в базу
SEEN_STEP = timedelta(minutes=1)

limiter = LoginLimiter()
router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])


def client_ip(request: Request) -> str | None:
    # Адрес клиента передаёт nginx; без него — адрес соединения
    return request.headers.get("X-Real-IP") or (request.client.host if request.client else None)


def _confirm_within(settings: Settings) -> timedelta:
    return timedelta(minutes=settings.admin_confirm_minutes)


async def cookie_session(
    request: Request, session: SessionDep, settings: SettingsDep
) -> AdminSession:
    """Сессия из куки в любом состоянии. Нет куки или она поддельная — 401."""
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Нужно войти")
    token = request.cookies.get(COOKIE)
    if not token:
        raise unauthorized
    try:
        user_id, session_id = decode_admin_token(token, settings.jwt_secret.get_secret_value())
    except TokenError:
        raise unauthorized from None
    admin_session = await admin_auth.get_session(session, session_id)
    if admin_session is None or admin_session.user_id != user_id:
        raise unauthorized
    return admin_session


CookieSession = Annotated[AdminSession, Depends(cookie_session)]


def _check_csrf(request: Request, admin_session: AdminSession) -> None:
    if request.method in SAFE_METHODS:
        return
    sent = request.headers.get(CSRF_HEADER, "")
    if not hmac.compare_digest(sent, admin_session.csrf_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет CSRF-токена")


@dataclass(frozen=True, slots=True)
class WebAdmin:
    user: User
    session: AdminSession


async def current_web_admin(
    request: Request, admin_session: CookieSession, session: SessionDep, settings: SettingsDep
) -> WebAdmin:
    """Админ с подтверждённым входом в веб-админку."""
    now = datetime.now(UTC)
    if admin_auth.state(admin_session, now, _confirm_within(settings)) is not SessionState.ACTIVE:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Вход не подтверждён")
    _check_csrf(request, admin_session)
    user = await get_user(session, admin_session.user_id)
    if user is None or user.is_deleted or user.telegram_id not in settings.admin_telegram_ids:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Нужно войти")
    if admin_session.last_seen_at is None or now - admin_session.last_seen_at >= SEEN_STEP:
        admin_session.last_seen_at = now
        await session.commit()
    return WebAdmin(user=user, session=admin_session)


CurrentWebAdmin = Annotated[WebAdmin, Depends(current_web_admin)]


class LoginIn(BaseModel):
    """Поля, которые Telegram Login Widget передаёт в onauth."""

    id: int
    first_name: str = ""
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str


class SessionOut(BaseModel):
    state: SessionState
    name: str
    expires_at: datetime
    # Только у подтверждённого входа: без него изменяющие запросы не пройдут
    csrf_token: str | None = None


class ActiveSessionOut(BaseModel):
    id: str
    ip: str | None
    user_agent: str | None
    created_at: datetime
    last_seen_at: datetime | None
    current: bool


def _session_out(
    admin_session: AdminSession, user: User, now: datetime, settings: Settings
) -> SessionOut:
    current = admin_auth.state(admin_session, now, _confirm_within(settings))
    return SessionOut(
        state=current,
        name=user.first_name,
        expires_at=admin_session.expires_at,
        csrf_token=admin_session.csrf_token if current is SessionState.ACTIVE else None,
    )


class ConfigOut(BaseModel):
    # Для Telegram Login Widget на странице входа
    bot_username: str


@router.get("/config")
async def config() -> ConfigOut:
    return ConfigOut(bot_username=await get_bot_username())


@router.post("/telegram")
async def login(
    body: LoginIn,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> SessionOut:
    now = datetime.now(UTC)
    ip = client_ip(request)
    if not limiter.allow(ip or "unknown", now):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Слишком много попыток входа")
    fields = {key: str(value) for key, value in body.model_dump().items() if value is not None}
    try:
        tg_user = validate_login_widget(
            fields, settings.bot_token.get_secret_value(), settings.admin_login_max_age
        )
    except InitDataError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверные данные Telegram") from None
    if tg_user.id not in settings.admin_telegram_ids:
        await admin_auth.audit(
            session, None, "login.rejected", payload={"telegram_id": tg_user.id}, ip=ip
        )
        await session.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Только для админа")

    user = await upsert_telegram_user(session, tg_user)
    admin_session = await admin_auth.create_session(
        session,
        user,
        now,
        timedelta(minutes=settings.admin_session_ttl_minutes),
        ip,
        request.headers.get("User-Agent"),
    )
    await admin_auth.audit(session, user.id, "login.requested", session_id=admin_session.id, ip=ip)
    await session.commit()
    try:
        await send_login_confirmation(get_bot(), tg_user.id, admin_session)
    except Exception:
        # Без сообщения в боте вход не подтвердить: закрываем сессию, чтобы не висела
        logger.exception("Admin login confirmation was not sent")
        await admin_auth.revoke(session, admin_session, now)
        await session.commit()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Не удалось отправить подтверждение в бот"
        ) from None

    token = create_access_token(
        user.id,
        settings.jwt_secret.get_secret_value(),
        settings.admin_session_ttl_minutes,
        audience=Audience.ADMIN,
        session_id=admin_session.id,
    )
    response.set_cookie(
        COOKIE,
        token,
        max_age=settings.admin_session_ttl_minutes * 60,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="strict",
        path="/api",
    )
    return _session_out(admin_session, user, now, settings)


@router.get("/session")
async def current_session(
    admin_session: CookieSession, session: SessionDep, settings: SettingsDep
) -> SessionOut:
    """Страница входа опрашивает его, пока админ не нажмёт кнопку в боте."""
    user = await get_user(session, admin_session.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Нужно войти")
    return _session_out(admin_session, user, datetime.now(UTC), settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request, response: Response, admin_session: CookieSession, session: SessionDep
) -> None:
    if admin_session.status == admin_auth.SessionStatus.ACTIVE:
        _check_csrf(request, admin_session)
    await admin_auth.revoke(session, admin_session, datetime.now(UTC))
    await admin_auth.audit(
        session,
        admin_session.user_id,
        "logout",
        session_id=admin_session.id,
        ip=client_ip(request),
    )
    await session.commit()
    response.delete_cookie(COOKIE, path="/api")


@router.get("/sessions")
async def sessions(admin: CurrentWebAdmin, session: SessionDep) -> list[ActiveSessionOut]:
    rows = await admin_auth.list_sessions(session, admin.user, datetime.now(UTC))
    return [
        ActiveSessionOut(
            id=row.id,
            ip=row.ip,
            user_agent=row.user_agent,
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
            current=row.id == admin.session.id,
        )
        for row in rows
    ]


@router.post("/sessions/{session_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: str, request: Request, admin: CurrentWebAdmin, session: SessionDep
) -> None:
    target = await admin_auth.get_session(session, session_id)
    if target is None or target.user_id != admin.user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сессии нет")
    await admin_auth.revoke(session, target, datetime.now(UTC))
    await admin_auth.audit(
        session,
        admin.user.id,
        "session.revoked",
        session_id=admin.session.id,
        target=f"session:{target.id[:8]}",
        ip=client_ip(request),
    )
    await session.commit()
