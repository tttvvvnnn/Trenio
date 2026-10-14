from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import make_init_data
from tests.test_api import login
from trenio.db.models import User, UserAvatar
from trenio.services import avatars
from trenio.services.avatars import TelegramPhoto

JPEG = b"\xff\xd8\xff\xe0" + b"photo" * 10


def photo(unique_id: str, body: bytes = b"tg") -> TelegramPhoto:
    return TelegramPhoto(unique_id=unique_id, data=avatars.JPEG_MAGIC + body)


async def me(client: AsyncClient, token: str) -> dict[str, Any]:
    response = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


async def test_login_pulls_photo_from_telegram(
    client: AsyncClient, telegram_photos: dict[int, Any]
) -> None:
    telegram_photos[7] = photo("a")
    token = await login(client, make_init_data(user_id=7))

    body = await me(client, token)
    assert body["avatar_mode"] == "telegram"
    url = body["avatar_url"]
    assert url.startswith("/api/avatars/")

    image = await client.get(url)
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    assert "immutable" in image.headers["cache-control"]
    assert image.content == avatars.JPEG_MAGIC + b"tg"


async def test_user_without_photo_has_no_avatar(client: AsyncClient) -> None:
    token = await login(client, make_init_data(user_id=7))
    assert (await me(client, token))["avatar_url"] is None


async def test_unknown_avatar_is_404(client: AsyncClient) -> None:
    assert (await client.get("/api/avatars/nope")).status_code == 404


async def test_refresh_once_a_day_and_only_on_change(
    session: AsyncSession, telegram_photos: dict[int, Any]
) -> None:
    user = User(telegram_id=7, first_name="Анна")
    session.add(user)
    await session.commit()
    now = datetime.now(UTC)

    telegram_photos[7] = photo("a")
    await avatars.refresh_from_telegram(session, user, now)
    first_key = user.avatar_key
    assert first_key is not None

    # В течение суток Telegram не спрашиваем, даже если фото поменялось
    telegram_photos[7] = photo("b", b"new")
    await avatars.refresh_from_telegram(session, user, now + timedelta(hours=1))
    assert user.avatar_key == first_key

    # То же фото через сутки: ключ прежний, кэш браузера не сбрасывается
    telegram_photos[7] = photo("a")
    await avatars.refresh_from_telegram(session, user, now + timedelta(days=1))
    assert user.avatar_key == first_key

    telegram_photos[7] = photo("b", b"new")
    await avatars.refresh_from_telegram(session, user, now + timedelta(days=2))
    assert user.avatar_key not in (None, first_key)
    assert await avatars.get_image(session, user.avatar_key or "") == avatars.JPEG_MAGIC + b"new"

    # Человек убрал фото в Telegram или скрыл его настройками приватности
    del telegram_photos[7]
    await avatars.refresh_from_telegram(session, user, now + timedelta(days=3))
    assert user.avatar_key is None
    assert await session.scalar(select(UserAvatar).where(UserAvatar.user_id == user.id)) is None


async def test_telegram_error_keeps_old_photo(
    session: AsyncSession, telegram_photos: dict[int, Any]
) -> None:
    user = User(telegram_id=7, first_name="Анна")
    session.add(user)
    await session.commit()
    now = datetime.now(UTC)
    telegram_photos[7] = photo("a")
    await avatars.refresh_from_telegram(session, user, now)
    key = user.avatar_key

    telegram_photos[7] = RuntimeError("Telegram недоступен")
    await avatars.refresh_from_telegram(session, user, now + timedelta(days=1))
    assert user.avatar_key == key


async def test_upload_own_photo_and_telegram_does_not_override(
    client: AsyncClient, telegram_photos: dict[int, Any]
) -> None:
    telegram_photos[7] = photo("a")
    token = await login(client, make_init_data(user_id=7))
    auth = {"Authorization": f"Bearer {token}", "Content-Type": "image/jpeg"}

    response = await client.put("/api/me/avatar", content=JPEG, headers=auth)
    assert response.status_code == 200, response.text
    assert response.json()["avatar_mode"] == "custom"
    url = response.json()["avatar_url"]
    assert (await client.get(url)).content == JPEG

    # Повторный вход не возвращает фото из Telegram
    telegram_photos[7] = photo("b")
    token = await login(client, make_init_data(user_id=7))
    body = await me(client, token)
    assert body["avatar_mode"] == "custom"
    assert body["avatar_url"] == url


async def test_upload_rejects_non_jpeg_and_too_big(client: AsyncClient) -> None:
    token = await login(client, make_init_data(user_id=7))
    auth = {"Authorization": f"Bearer {token}", "Content-Type": "image/jpeg"}

    response = await client.put("/api/me/avatar", content=b"<svg></svg>", headers=auth)
    assert response.status_code == 415
    big = avatars.JPEG_MAGIC + b"0" * avatars.MAX_BYTES
    response = await client.put("/api/me/avatar", content=big, headers=auth)
    assert response.status_code == 413
    assert (await me(client, token))["avatar_url"] is None


async def test_remove_and_return_to_telegram(
    client: AsyncClient, telegram_photos: dict[int, Any]
) -> None:
    telegram_photos[7] = photo("a")
    token = await login(client, make_init_data(user_id=7))
    auth = {"Authorization": f"Bearer {token}"}
    old_url = (await me(client, token))["avatar_url"]

    response = await client.delete("/api/me/avatar", headers=auth)
    assert response.json() == {"avatar_url": None, "avatar_mode": "none"}
    assert (await client.get(old_url)).status_code == 404
    # Убранное фото не возвращается само при следующем входе
    token = await login(client, make_init_data(user_id=7))
    assert (await me(client, token))["avatar_url"] is None

    response = await client.post("/api/me/avatar/telegram", headers=auth)
    assert response.json()["avatar_mode"] == "telegram"
    assert response.json()["avatar_url"] is not None
