"""Наши собственные токены доступа.

initData живёт только внутри Telegram, а JWT подойдёт и будущему
мобильному приложению: способ входа меняется, токен остаётся тем же.
"""

from datetime import UTC, datetime, timedelta

import jwt

ALGORITHM = "HS256"


class TokenError(ValueError):
    """Токен недействителен или истёк."""


def create_access_token(user_id: int, secret: str, ttl_minutes: int) -> str:
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=ttl_minutes)}
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_access_token(token: str, secret: str) -> int:
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise TokenError(str(exc)) from exc
