import hmac
from typing import Annotated, Any

from aiogram.types import Update
from fastapi import APIRouter, Header, HTTPException, status

from trenio.api.deps import SettingsDep
from trenio.bot.setup import WEBHOOK_PATH, get_bot, get_dispatcher

router = APIRouter(include_in_schema=False)


@router.post(WEBHOOK_PATH)
async def bot_webhook(
    payload: dict[str, Any],
    settings: SettingsDep,
    secret: Annotated[str, Header(alias="X-Telegram-Bot-Api-Secret-Token")] = "",
) -> dict[str, bool]:
    # Telegram присылает секрет, заданный в set_webhook; чужие запросы отбрасываем
    expected = settings.webhook_secret.get_secret_value()
    if expected and not hmac.compare_digest(secret, expected):
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    bot = get_bot()
    update = Update.model_validate(payload, context={"bot": bot})
    await get_dispatcher().feed_update(bot, update)
    return {"ok": True}
