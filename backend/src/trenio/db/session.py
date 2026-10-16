from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# realtime подписывается на commit всех сессий: сигналы «данные поменялись»
import trenio.realtime  # noqa: F401
from trenio.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    # Маленький пул: на сервере мало памяти, а нагрузка у беты небольшая
    return create_async_engine(
        get_settings().database_url, pool_size=5, max_overflow=5, pool_pre_ping=True
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session
