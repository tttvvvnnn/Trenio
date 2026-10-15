"""Фото пользователей: берём из Telegram, человек может заменить своим или убрать.

Картинка лежит в базе (user_avatars), а в users только ключ для адреса /api/avatars/<ключ>.
Ключ случайный и меняется с каждым новым фото: адрес нельзя угадать, а браузер и
Telegram кэшируют картинку навсегда.
"""

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.db.models import User, UserAvatar

logger = logging.getLogger(__name__)

# Своё фото не больше 512 КБ; Mini App сжимает его до 320×320, это около 30 КБ
MAX_BYTES = 512 * 1024
# Фото из Telegram проверяем не чаще раза в сутки
REFRESH_INTERVAL = timedelta(days=1)
# Какой размер брать из Telegram: он отдаёт 160, 320 и 640 точек
TELEGRAM_SIZE = 320

JPEG_MAGIC = b"\xff\xd8\xff"


class AvatarMode(StrEnum):
    TELEGRAM = "telegram"
    CUSTOM = "custom"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class TelegramPhoto:
    # file_unique_id: одинаковый у одного и того же фото, даже если бот другой
    unique_id: str
    data: bytes


def avatar_url(user: User) -> str | None:
    return f"/api/avatars/{user.avatar_key}" if user.avatar_key else None


def is_jpeg(data: bytes) -> bool:
    return data.startswith(JPEG_MAGIC)


async def telegram_photo(telegram_id: int) -> TelegramPhoto | None:
    """Текущее фото профиля из Telegram. None — фото нет или человек его скрыл."""
    # Импорт здесь: бот тянет обработчики, а они сами пользуются этим модулем
    from trenio.bot.setup import get_bot

    bot = get_bot()
    photos = await bot.get_user_profile_photos(telegram_id, limit=1)
    if not photos.photos:
        return None
    sizes = photos.photos[0]
    # Самый маленький не меньше 320 точек, а если таких нет — самый большой
    fitting = [size for size in sizes if size.width >= TELEGRAM_SIZE]
    size = min(fitting, key=lambda s: s.width) if fitting else max(sizes, key=lambda s: s.width)
    downloaded = await bot.download(size)
    if downloaded is None:
        return None
    return TelegramPhoto(unique_id=size.file_unique_id, data=downloaded.read())


async def _store(session: AsyncSession, user: User, data: bytes) -> None:
    await session.execute(
        insert(UserAvatar)
        .values(user_id=user.id, data=data)
        .on_conflict_do_update(index_elements=[UserAvatar.user_id], set_={"data": data})
    )
    user.avatar_key = secrets.token_urlsafe(16)


async def forget(session: AsyncSession, user: User) -> None:
    """Удаляет своё фото и забывает фото из Telegram. Коммит — за вызывающим."""
    await session.execute(delete(UserAvatar).where(UserAvatar.user_id == user.id))
    user.avatar_key = None
    user.avatar_telegram_id = None


async def refresh_from_telegram(
    session: AsyncSession, user: User, now: datetime, force: bool = False
) -> None:
    """Подтягивает фото из Telegram, если человек его не заменял и давно не проверяли.

    Ошибки Telegram не мешают входу: фото останется прежним, попробуем через сутки.
    """
    if user.telegram_id is None or user.avatar_mode != AvatarMode.TELEGRAM:
        return
    checked = user.avatar_checked_at
    if not force and checked is not None and now - checked < REFRESH_INTERVAL:
        return
    try:
        photo = await telegram_photo(user.telegram_id)
    except Exception:
        logger.warning("Не удалось получить фото пользователя %s из Telegram", user.id)
        photo = None
        failed = True
    else:
        failed = False
    # Пока качали, человек мог загрузить своё фото: перечитываем строку под блокировкой
    await session.refresh(user, with_for_update=True)
    if user.avatar_mode == AvatarMode.TELEGRAM and not failed:
        if photo is None:
            await forget(session, user)
        elif photo.unique_id != user.avatar_telegram_id or user.avatar_key is None:
            await _store(session, user, photo.data)
            user.avatar_telegram_id = photo.unique_id
    user.avatar_checked_at = now
    await session.commit()


async def refresh_in_background(user_id: int, now: datetime) -> None:
    """То же для фоновой задачи после входа: со своей сессией, без ошибок наружу."""
    from trenio.db.session import get_sessionmaker

    try:
        async with get_sessionmaker()() as session:
            user = await session.get(User, user_id)
            if user is not None:
                await refresh_from_telegram(session, user, now)
    except Exception:
        logger.exception("Не удалось обновить фото пользователя %s", user_id)


async def set_custom(session: AsyncSession, user: User, data: bytes) -> None:
    """Своё фото вместо телеграмного. Формат и размер проверяет вызывающий."""
    await _store(session, user, data)
    user.avatar_mode = AvatarMode.CUSTOM
    user.avatar_telegram_id = None
    await session.commit()


async def remove(session: AsyncSession, user: User) -> None:
    """Убрать фото совсем: вместо него будут инициалы, из Telegram больше не берём."""
    await forget(session, user)
    user.avatar_mode = AvatarMode.NONE
    await session.commit()


async def use_telegram(session: AsyncSession, user: User, now: datetime) -> None:
    """Вернуться к фото из Telegram и сразу его подтянуть."""
    if user.avatar_mode != AvatarMode.TELEGRAM:
        await forget(session, user)
        user.avatar_mode = AvatarMode.TELEGRAM
        await session.commit()
    await refresh_from_telegram(session, user, now, force=True)


async def get_image(session: AsyncSession, key: str) -> bytes | None:
    return await session.scalar(
        select(UserAvatar.data)
        .join(User, User.id == UserAvatar.user_id)
        .where(User.avatar_key == key)
    )
