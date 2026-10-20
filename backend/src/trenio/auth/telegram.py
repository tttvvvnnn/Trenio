"""Проверка подписи initData, которую Telegram передаёт в Mini App.

Алгоритм из документации Telegram:
https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl


class InitDataError(ValueError):
    """initData подделана, повреждена или устарела."""


@dataclass(frozen=True, slots=True)
class TelegramUser:
    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None


def _secret_key(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def sign_init_data(fields: dict[str, str], bot_token: str) -> str:
    """Считает hash для набора полей. Нужен тестам и для понимания алгоритма."""
    data_check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    return hmac.new(_secret_key(bot_token), data_check_string.encode(), hashlib.sha256).hexdigest()


def validate_init_data(
    init_data: str, bot_token: str, max_age: int, now: float | None = None
) -> TelegramUser:
    """Проверяет подпись и свежесть initData и возвращает пользователя Telegram."""
    if not bot_token:
        raise InitDataError("bot token is not configured")

    fields = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
    received_hash = fields.pop("hash", None)
    if not received_hash:
        raise InitDataError("hash is missing")

    expected_hash = sign_init_data(fields, bot_token)
    # compare_digest сравнивает за постоянное время, чтобы не подсказывать подпись по таймингу
    if not hmac.compare_digest(expected_hash, received_hash):
        raise InitDataError("signature mismatch")

    try:
        auth_date = int(fields["auth_date"])
    except (KeyError, ValueError) as exc:
        raise InitDataError("auth_date is missing") from exc
    current = time.time() if now is None else now
    if current - auth_date > max_age:
        raise InitDataError("init data is expired")

    try:
        raw_user = json.loads(fields["user"])
        return TelegramUser(
            id=int(raw_user["id"]),
            first_name=str(raw_user.get("first_name", "")),
            last_name=raw_user.get("last_name"),
            username=raw_user.get("username"),
            language_code=raw_user.get("language_code"),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise InitDataError("user is missing or malformed") from exc


def sign_login_widget(fields: dict[str, str], bot_token: str) -> str:
    """hash для данных Telegram Login Widget. Ключ другой, чем у Mini App: sha256 от токена.

    https://core.telegram.org/widgets/login#checking-authorization
    """
    data_check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hashlib.sha256(bot_token.encode()).digest()
    return hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()


def validate_login_widget(
    fields: dict[str, str], bot_token: str, max_age: int, now: float | None = None
) -> TelegramUser:
    """Проверяет подпись и свежесть данных виджета входа на сайте."""
    if not bot_token:
        raise InitDataError("bot token is not configured")
    fields = dict(fields)
    received_hash = fields.pop("hash", None)
    if not received_hash:
        raise InitDataError("hash is missing")
    if not hmac.compare_digest(sign_login_widget(fields, bot_token), received_hash):
        raise InitDataError("signature mismatch")
    try:
        auth_date = int(fields["auth_date"])
        user_id = int(fields["id"])
    except (KeyError, ValueError) as exc:
        raise InitDataError("auth_date or id is missing") from exc
    current = time.time() if now is None else now
    if current - auth_date > max_age:
        raise InitDataError("login data is expired")
    return TelegramUser(
        id=user_id,
        first_name=fields.get("first_name", ""),
        last_name=fields.get("last_name"),
        username=fields.get("username"),
    )
