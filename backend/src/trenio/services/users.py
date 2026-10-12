from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.auth.telegram import TelegramUser
from trenio.db.models import User


async def upsert_telegram_user(session: AsyncSession, tg_user: TelegramUser) -> User:
    """Создаёт пользователя при первом входе или обновляет имя и username."""
    values = {
        "telegram_id": tg_user.id,
        "first_name": tg_user.first_name,
        "last_name": tg_user.last_name,
        "username": tg_user.username,
        "language_code": tg_user.language_code,
    }
    # ON CONFLICT защищает от гонки, когда бот и Mini App создают пользователя одновременно
    stmt = (
        insert(User)
        .values(**values)
        .on_conflict_do_update(
            index_elements=[User.telegram_id], set_={**values, "updated_at": func.now()}
        )
        .returning(User)
    )
    user = (await session.scalars(stmt)).one()
    await session.commit()
    return user


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    return await session.scalar(select(User).where(User.id == user_id))
