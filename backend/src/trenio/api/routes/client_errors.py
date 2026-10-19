import logging
from datetime import UTC, datetime
from importlib.metadata import version

from fastapi import APIRouter, BackgroundTasks, status
from pydantic import BaseModel, Field

from trenio.api.deps import CurrentUser, SessionDep, SettingsDep
from trenio.bot.setup import get_bot
from trenio.services import client_errors
from trenio.services.trainers import get_active_trainer

router = APIRouter(tags=["errors"])
logger = logging.getLogger(__name__)


class ClientErrorIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    stack: str | None = Field(default=None, max_length=2000)
    # Где случилось: компонент или «window» для ошибок вне отрисовки
    screen: str | None = Field(default=None, max_length=100)


async def send_to_admins(admin_ids: frozenset[int], text: str) -> None:
    bot = get_bot()
    for chat_id in admin_ids:
        try:
            await bot.send_message(chat_id, text)
        except Exception:
            # Не дошло — не страшно: ошибка останется в журнале сервера
            logger.exception("could not send client error to admin %s", chat_id)


@router.post("/client-errors", status_code=status.HTTP_204_NO_CONTENT)
async def report_client_error(
    body: ClientErrorIn,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    tasks: BackgroundTasks,
) -> None:
    """Mini App сообщает о своей ошибке; админы получают её в Telegram."""
    logger.warning("client error from user %s: %s", user.id, body.message)
    now = datetime.now(UTC)
    await client_errors.save(session, user.id, body.message, body.screen, now)
    await session.commit()
    if not settings.admin_telegram_ids:
        return
    if not client_errors.limiter.allow(body.message, now):
        return
    trainer = await get_active_trainer(session, user.id)
    text = client_errors.error_text(
        message=body.message,
        stack=body.stack,
        screen=body.screen,
        user_id=user.id,
        role="тренер" if trainer is not None else "клиент",
        version=version("trenio"),
        env=settings.env,
    )
    tasks.add_task(send_to_admins, settings.admin_telegram_ids, text)
