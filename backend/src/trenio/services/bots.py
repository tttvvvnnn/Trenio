"""Боты, через которые работают специалисты. Пока бот один — основной."""

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.db.models import MAIN_BOT_ID, Bot


async def sync_main_bot(session: AsyncSession, external_id: int, username: str | None) -> None:
    """Записывает id и имя основного бота из Telegram: токен мог смениться на другого бота,
    а без id админка не сопоставит его с ботами специалистов."""
    await session.execute(
        update(Bot).where(Bot.id == MAIN_BOT_ID).values(external_id=external_id, username=username)
    )
    await session.commit()
