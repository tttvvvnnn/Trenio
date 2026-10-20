"""Наши собственные токены доступа.

initData живёт только внутри Telegram, а JWT подойдёт и будущему
мобильному приложению: способ входа меняется, токен остаётся тем же.

У токена есть назначение (aud): app — Mini App и приложения, admin — веб-админка.
Токен одного назначения не пускает в другое, даже если подписан тем же ключом.
"""

from datetime import UTC, datetime, timedelta
from enum import StrEnum

import jwt

ALGORITHM = "HS256"


class Audience(StrEnum):
    APP = "app"
    ADMIN = "admin"


class TokenError(ValueError):
    """Токен недействителен или истёк."""


def create_access_token(
    user_id: int, secret: str, ttl_minutes: int, audience: Audience = Audience.APP
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "aud": audience.value,
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_access_token(token: str, secret: str, audience: Audience = Audience.APP) -> int:
    try:
        # aud проверяем сами: токены Mini App, выданные до его появления, считаем app,
        # пока они не истекут сами
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM], options={"verify_aud": False})
        if payload.get("aud", Audience.APP.value) != audience.value:
            raise TokenError("wrong audience")
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise TokenError(str(exc)) from exc
