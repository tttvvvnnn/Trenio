from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.auth.telegram import TelegramUser
from trenio.db.models import User
from trenio.services.notifications import Role


async def upsert_telegram_user(session: AsyncSession, tg_user: TelegramUser) -> User:
    """Создаёт пользователя при первом входе или обновляет имя и username.

    Если человек задал своё имя в профиле, имя из Telegram только запоминаем.
    """
    values = {
        "telegram_id": tg_user.id,
        "first_name": tg_user.first_name,
        "last_name": tg_user.last_name,
        "telegram_first_name": tg_user.first_name,
        "telegram_last_name": tg_user.last_name,
        "username": tg_user.username,
        "language_code": tg_user.language_code,
    }
    insert_stmt = insert(User).values(**values)
    excluded = insert_stmt.excluded
    updates = {
        **values,
        "first_name": case((User.name_custom, User.first_name), else_=excluded.first_name),
        "last_name": case((User.name_custom, User.last_name), else_=excluded.last_name),
        "updated_at": func.now(),
    }
    # ON CONFLICT защищает от гонки, когда бот и Mini App создают пользователя одновременно
    stmt = insert_stmt.on_conflict_do_update(
        index_elements=[User.telegram_id], set_=updates
    ).returning(User)
    user = (await session.scalars(stmt)).one()
    await session.commit()
    return user


async def set_name(
    session: AsyncSession, user: User, first_name: str, last_name: str | None
) -> None:
    """Своё имя, которое видят тренеры. Telegram его больше не перезаписывает."""
    user.first_name = first_name
    user.last_name = last_name
    user.name_custom = True
    await session.commit()


async def reset_name(session: AsyncSession, user: User) -> None:
    """Обратно к имени из Telegram."""
    if user.telegram_first_name:
        user.first_name = user.telegram_first_name
        user.last_name = user.telegram_last_name
    user.name_custom = False
    await session.commit()


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    return await session.scalar(select(User).where(User.id == user_id))


async def finish_tour(session: AsyncSession, user: User, role: Role, now: datetime) -> None:
    """Отмечает вводный тур роли пройденным; повторный проход время не меняет."""
    if role is Role.TRAINER:
        user.trainer_tour_at = user.trainer_tour_at or now
    else:
        user.client_tour_at = user.client_tour_at or now
    await session.commit()
