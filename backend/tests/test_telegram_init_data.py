import time
from urllib.parse import parse_qsl, urlencode

import pytest

from tests.factories import BOT_TOKEN, make_init_data
from trenio.auth.telegram import InitDataError, validate_init_data

DAY = 24 * 60 * 60


def test_valid_init_data_returns_user() -> None:
    user = validate_init_data(make_init_data(user_id=7, first_name="Анна"), BOT_TOKEN, DAY)
    assert user.id == 7
    assert user.first_name == "Анна"
    assert user.username == "ivan"


def test_matches_aiogram_implementation() -> None:
    # Независимая сверка: aiogram реализует тот же алгоритм Telegram
    from aiogram.utils.web_app import safe_parse_webapp_init_data

    init_data = make_init_data(user_id=7)
    parsed = safe_parse_webapp_init_data(BOT_TOKEN, init_data)
    assert parsed.user is not None
    assert parsed.user.id == validate_init_data(init_data, BOT_TOKEN, DAY).id


def test_tampered_user_is_rejected() -> None:
    fields = dict(parse_qsl(make_init_data(user_id=7)))
    fields["user"] = fields["user"].replace('"id":7', '"id":8')
    with pytest.raises(InitDataError, match="signature"):
        validate_init_data(urlencode(fields), BOT_TOKEN, DAY)


def test_other_bot_token_is_rejected() -> None:
    with pytest.raises(InitDataError, match="signature"):
        validate_init_data(make_init_data(bot_token="999:OTHER"), BOT_TOKEN, DAY)


def test_missing_hash_is_rejected() -> None:
    fields = dict(parse_qsl(make_init_data()))
    del fields["hash"]
    with pytest.raises(InitDataError, match="hash"):
        validate_init_data(urlencode(fields), BOT_TOKEN, DAY)


def test_expired_init_data_is_rejected() -> None:
    old = int(time.time()) - DAY - 60
    with pytest.raises(InitDataError, match="expired"):
        validate_init_data(make_init_data(auth_date=old), BOT_TOKEN, DAY)


def test_empty_bot_token_is_rejected() -> None:
    with pytest.raises(InitDataError):
        validate_init_data(make_init_data(), "", DAY)
