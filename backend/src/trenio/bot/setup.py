from functools import lru_cache

from aiogram import Bot, Dispatcher

from trenio.bot import actions, admin, handlers
from trenio.config import get_settings

WEBHOOK_PATH = "/bot/webhook"


@lru_cache
def get_bot() -> Bot:
    return Bot(token=get_settings().bot_token.get_secret_value())


async def get_bot_username() -> str:
    """Имя бота для ссылок t.me/<имя>. aiogram кэширует ответ getMe после первого запроса."""
    me = await get_bot().me()
    return me.username or ""


@lru_cache
def get_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(admin.router)
    dispatcher.include_router(handlers.router)
    dispatcher.include_router(actions.router)
    return dispatcher


async def configure_webhook(bot: Bot) -> None:
    settings = get_settings()
    await bot.set_webhook(
        url=settings.webhook_base_url.rstrip("/") + WEBHOOK_PATH,
        secret_token=settings.webhook_secret.get_secret_value() or None,
        allowed_updates=get_dispatcher().resolve_used_update_types(),
    )
