import pytest

from trenio.auth.tokens import TokenError, create_access_token, decode_access_token

SECRET = "test-secret-with-enough-length-for-hs256"


def test_roundtrip() -> None:
    token = create_access_token(15, SECRET, ttl_minutes=5)
    assert decode_access_token(token, SECRET) == 15


def test_wrong_secret() -> None:
    token = create_access_token(15, SECRET, ttl_minutes=5)
    with pytest.raises(TokenError):
        decode_access_token(token, SECRET + "x")


def test_expired() -> None:
    token = create_access_token(15, SECRET, ttl_minutes=-1)
    with pytest.raises(TokenError):
        decode_access_token(token, SECRET)


def test_server_env_requires_real_secret() -> None:
    from pydantic import ValidationError

    from trenio.config import Settings

    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(env="prod", jwt_secret="")
    assert Settings(env="prod", jwt_secret=SECRET).env == "prod"


def test_admin_token_does_not_open_app() -> None:
    from trenio.auth.tokens import Audience

    admin = create_access_token(15, SECRET, ttl_minutes=5, audience=Audience.ADMIN)
    assert decode_access_token(admin, SECRET, audience=Audience.ADMIN) == 15
    with pytest.raises(TokenError):
        decode_access_token(admin, SECRET)
    app = create_access_token(15, SECRET, ttl_minutes=5)
    with pytest.raises(TokenError):
        decode_access_token(app, SECRET, audience=Audience.ADMIN)


def test_old_token_without_audience_is_app() -> None:
    from datetime import UTC, datetime, timedelta

    import jwt

    from trenio.auth.tokens import Audience

    now = datetime.now(UTC)
    old = jwt.encode(
        {"sub": "15", "iat": now, "exp": now + timedelta(minutes=5)}, SECRET, algorithm="HS256"
    )
    assert decode_access_token(old, SECRET) == 15
    with pytest.raises(TokenError):
        decode_access_token(old, SECRET, audience=Audience.ADMIN)
