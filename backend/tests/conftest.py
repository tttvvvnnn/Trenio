"""Общие фикстуры.

Тесты с базой запускаются, только если задан TEST_DATABASE_URL
(в CI его даёт service-контейнер PostgreSQL). Без него они пропускаются.
"""

import os
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import BOT_TOKEN

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
ADMIN_TELEGRAM_ID = 1001


def _reset_caches() -> None:
    from trenio.bot.setup import get_bot, get_dispatcher
    from trenio.config import get_settings
    from trenio.db.session import get_engine, get_sessionmaker

    for cached in (get_settings, get_engine, get_sessionmaker, get_bot, get_dispatcher):
        cached.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def test_env() -> Iterator[None]:
    env = {
        "ENV": "test",
        "BOT_TOKEN": BOT_TOKEN,
        "BOT_MODE": "polling",
        "JWT_SECRET": "test-secret-with-enough-length-for-hs256",
        "ADMIN_TELEGRAM_IDS": str(ADMIN_TELEGRAM_ID),
        "DATABASE_URL": TEST_DATABASE_URL or "postgresql+asyncpg://invalid/invalid",
    }
    previous = {key: os.environ.get(key) for key in env}
    os.environ.update(env)
    _reset_caches()
    yield
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    _reset_caches()


@pytest.fixture(scope="session")
def migrated_db(test_env: None) -> None:
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL не задан")
    from trenio.__main__ import run_migrations

    # Заодно проверяем, что миграции применяются на чистую базу
    run_migrations()


@pytest.fixture
async def clean_db(migrated_db: None) -> None:
    from trenio.db.session import get_engine

    # CASCADE чистит и всё, что ссылается на users: тренеров, приглашения
    async with get_engine().begin() as conn:
        await conn.execute(text("TRUNCATE users RESTART IDENTITY CASCADE"))
        await conn.execute(text("TRUNCATE app_settings"))
        await conn.execute(text("TRUNCATE admin_audit_log"))
        await conn.execute(text("TRUNCATE broadcasts RESTART IDENTITY"))
        await conn.execute(text("TRUNCATE promo_codes RESTART IDENTITY CASCADE"))


@pytest.fixture
async def session(clean_db: None) -> AsyncIterator[AsyncSession]:
    from trenio.db.session import get_sessionmaker

    async with get_sessionmaker()() as db:
        yield db


@pytest.fixture
async def client(clean_db: None) -> AsyncIterator[AsyncClient]:
    from trenio.api.app import Component, create_app

    # Бот и планировщик в тестах не нужны: они ходят в Telegram
    app = create_app(frozenset({Component.API}))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.fixture(autouse=True)
def telegram_photos(monkeypatch: pytest.MonkeyPatch) -> dict[int, Any]:
    """Фото профилей «в Telegram» по telegram_id: TelegramPhoto или исключение.

    Настоящий Telegram в тестах недоступен; по умолчанию фото ни у кого нет.
    """
    from trenio.services import avatars

    photos: dict[int, Any] = {}

    async def fake(telegram_id: int) -> avatars.TelegramPhoto | None:
        photo = photos.get(telegram_id)
        if isinstance(photo, Exception):
            raise photo
        return photo

    monkeypatch.setattr(avatars, "telegram_photo", fake)
    return photos
