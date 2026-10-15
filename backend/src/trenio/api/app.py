"""Сборка FastAPI-приложения из нужных частей.

Один образ, разные роли: в компактной схеме всё работает в одном процессе
(all-in-one), а при переезде на большой сервер те же части запускаются
отдельными контейнерами. Меняется только команда запуска в compose.
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from enum import StrEnum

from fastapi import APIRouter, FastAPI

from trenio.api.routes import (
    admin,
    auth,
    avatars,
    bookings,
    bot_webhook,
    client,
    finance,
    health,
    me,
    packages,
    privacy,
    schedule,
    stats,
    trainer,
)
from trenio.bot.setup import configure_webhook, get_bot, get_dispatcher
from trenio.config import BotMode, get_settings
from trenio.scheduler.setup import create_scheduler

logger = logging.getLogger(__name__)


class Component(StrEnum):
    API = "api"
    BOT = "bot"
    SCHEDULER = "scheduler"


ALL_COMPONENTS = frozenset(Component)


def create_app(components: frozenset[Component] = ALL_COMPONENTS) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        polling: asyncio.Task[None] | None = None
        scheduler, sender = (
            create_scheduler() if Component.SCHEDULER in components else (None, None)
        )

        if Component.BOT in components:
            bot = get_bot()
            if settings.bot_mode is BotMode.WEBHOOK:
                await configure_webhook(bot)
            else:
                # Без домена webhook невозможен, поэтому локально бот опрашивает Telegram сам
                await bot.delete_webhook()
                polling = asyncio.create_task(
                    get_dispatcher().start_polling(bot, handle_signals=False)
                )
        if scheduler is not None and sender is not None:
            # События из API этого процесса уходят сразу, не дожидаясь планового прохода
            sender.register()
            scheduler.start()
        logger.info("Trenio started: %s", ", ".join(sorted(components)))
        try:
            yield
        finally:
            if scheduler is not None and sender is not None:
                sender.unregister()
                scheduler.shutdown(wait=False)
            if polling is not None:
                await get_dispatcher().stop_polling()
                with contextlib.suppress(asyncio.CancelledError):
                    await polling
            if Component.BOT in components or Component.SCHEDULER in components:
                await get_bot().session.close()

    app = FastAPI(title="Trenio API", version="0.1.0", lifespan=lifespan)
    # /health есть в любой роли: по нему деплой проверяет, что контейнер жив
    app.include_router(health.router)

    if Component.API in components:
        api = APIRouter(prefix="/api")
        api.include_router(auth.router)
        api.include_router(me.router)
        api.include_router(avatars.router)
        api.include_router(trainer.router)
        api.include_router(schedule.router)
        api.include_router(bookings.router)
        api.include_router(client.router)
        api.include_router(packages.router)
        api.include_router(finance.router)
        api.include_router(admin.router)
        api.include_router(privacy.router)
        api.include_router(stats.router)
        app.include_router(api)
    if Component.BOT in components and settings.bot_mode is BotMode.WEBHOOK:
        app.include_router(bot_webhook.router)
    return app
