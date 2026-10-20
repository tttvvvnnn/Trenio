"""Наши собственные токены доступа.

initData живёт только внутри Telegram, а JWT подойдёт и будущему
мобильному приложению: способ входа меняется, токен остаётся тем же.

У токена есть назначение (aud): app — Mini App и приложения, admin — веб-админка.
Токен одного назначения не пускает в другое, даже если подписан тем же ключом.
"""

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import jwt

ALGORITHM = "HS256"


class Audience(StrEnum):
    APP = "app"
    ADMIN = "admin"


class TokenError(ValueError):
    """Токен недействителен или истёк."""


def create_access_token(
    user_id: int,
    secret: str,
    ttl_minutes: int,
    audience: Audience = Audience.APP,
    session_id: str | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "aud": audience.value,
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
    }
    if session_id is not None:
        # Вход в админку можно отозвать: токен действует, пока жива его сессия в базе
        payload["sid"] = session_id
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def _decode(token: str, secret: str, audience: Audience) -> dict[str, Any]:
    try:
        # aud проверяем сами: токены Mini App, выданные до его появления, считаем app,
        # пока они не истекут сами
        payload: dict[str, Any] = jwt.decode(
            token, secret, algorithms=[ALGORITHM], options={"verify_aud": False}
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if payload.get("aud", Audience.APP.value) != audience.value:
        raise TokenError("wrong audience")
    return payload


def decode_access_token(token: str, secret: str, audience: Audience = Audience.APP) -> int:
    payload = _decode(token, secret, audience)
    try:
        return int(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise TokenError(str(exc)) from exc


def decode_admin_token(token: str, secret: str) -> tuple[int, str]:
    """id пользователя и id сессии из токена веб-админки."""
    payload = _decode(token, secret, Audience.ADMIN)
    try:
        return int(payload["sub"]), str(payload["sid"])
    except (KeyError, ValueError) as exc:
        raise TokenError(str(exc)) from exc
