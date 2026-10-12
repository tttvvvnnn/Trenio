"""Общие фикстуры.

Тесты с базой запускаются, только если задан TEST_DATABASE_URL
(в CI его даёт service-контейнер PostgreSQL). Без него они пропускаются.
"""

import os
from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from tests.factories import BOT_TOKEN

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
TRAINER_TELEGRAM_ID = 1001


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
        "BETA_TRAINER_IDS": str(TRAINER_TELEGRAM_ID),
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
async def client(migrated_db: None) -> AsyncIterator[AsyncClient]:
    from trenio.api.app import Component, create_app
    from trenio.db.session import get_engine

    async with get_engine().begin() as conn:
        await conn.execute(text("TRUNCATE users RESTART IDENTITY CASCADE"))
    # Бот и планировщик в тестах не нужны: они ходят в Telegram
    app = create_app(frozenset({Component.API}))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
