import json
import time
from urllib.parse import urlencode

from trenio.auth.telegram import sign_init_data, sign_login_widget

BOT_TOKEN = "123456:TEST-TOKEN"


def make_init_data(
    user_id: int = 42,
    first_name: str = "Иван",
    auth_date: int | None = None,
    bot_token: str = BOT_TOKEN,
) -> str:
    """Собирает initData так же, как это делает Telegram."""
    fields = {
        "auth_date": str(int(time.time()) if auth_date is None else auth_date),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(
            {"id": user_id, "first_name": first_name, "username": "ivan", "language_code": "ru"},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
    fields["hash"] = sign_init_data(fields, bot_token)
    return urlencode(fields)


def make_login_widget(
    user_id: int = 42,
    first_name: str = "Иван",
    auth_date: int | None = None,
    bot_token: str = BOT_TOKEN,
) -> dict[str, str | int]:
    """Данные Telegram Login Widget с подписью, как их отдаёт виджет на сайте."""
    fields = {
        "id": str(user_id),
        "first_name": first_name,
        "username": "ivan",
        "auth_date": str(int(time.time()) if auth_date is None else auth_date),
    }
    fields["hash"] = sign_login_widget(fields, bot_token)
    return {**fields, "id": user_id, "auth_date": int(fields["auth_date"])}
