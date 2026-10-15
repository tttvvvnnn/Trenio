"""Отправщик очереди уведомлений.

Каждое уведомление обрабатывается в своей транзакции:
SELECT ... FOR UPDATE SKIP LOCKED → отправка → status=sent → COMMIT.
Пока строка заблокирована, второй отправщик (другой процесс или контейнер) её пропускает,
а после коммита она уже не pending. Если процесс упадёт до коммита, блокировка снимется
и строку отправит следующий проход. Повтор возможен, только если процесс умрёт в
миллисекунды между ответом Telegram и коммитом: у Telegram нет защиты от повторной отправки.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trenio.db.models import Notification, User
from trenio.delivery import kick as kick_hook
from trenio.delivery.channel import Channel, DeliveryError
from trenio.delivery.texts import render
from trenio.services.notifications import Status

logger = logging.getLogger(__name__)

# После стольких сбоев сети уведомление считается недоставленным
MAX_ATTEMPTS = 5
# Не больше стольких сообщений за проход, чтобы не упереться в лимиты Telegram
BATCH = 100


def retry_delay(attempts: int) -> timedelta:
    # 2, 4, 8, 16 минут
    return timedelta(minutes=2**attempts)


async def send_one(session: AsyncSession, channel: Channel, now: datetime) -> bool:
    """Отправляет одно наступившее уведомление. False — в очереди пусто."""
    row = await session.scalar(
        select(Notification)
        .where(Notification.status == Status.PENDING, Notification.send_at <= now)
        .order_by(Notification.send_at, Notification.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if row is None:
        return False
    try:
        message = await render(session, row, now)
        if message is None:
            row.status = Status.SKIPPED
            return True
        user = await session.get(User, row.user_id)
        assert user is not None
        if user.is_offline:
            # Клиент без Telegram: писать некуда. Если он привяжет Telegram,
            # напоминания о будущих занятиях поставятся заново
            row.status = Status.SKIPPED
            return True
        await channel.send(user, message)
    except DeliveryError as error:
        _fail(row, str(error), error.permanent, now)
        return True
    except Exception as error:
        # Ошибка в одном сообщении не должна стопорить очередь
        logger.exception("Notification %s failed", row.id)
        _fail(row, repr(error), False, now)
        return True
    row.status = Status.SENT
    row.sent_at = now
    return True


def _fail(row: Notification, error: str, permanent: bool, now: datetime) -> None:
    row.attempts += 1
    row.error = error[:1000]
    if permanent or row.attempts >= MAX_ATTEMPTS:
        row.status = Status.FAILED
        logger.warning("Notification %s not delivered: %s", row.id, error)
    else:
        row.send_at = now + retry_delay(row.attempts)


async def dispatch_due(
    sessionmaker: async_sessionmaker[AsyncSession], channel: Channel, now: datetime
) -> int:
    """Отправляет всё, чему пришло время. Возвращает, сколько строк обработано."""
    done = 0
    while done < BATCH:
        async with sessionmaker() as session, session.begin():
            if not await send_one(session, channel, now):
                break
        done += 1
    return done


class Sender:
    """Отправщик в этом процессе: плановый проход раз в минуту и срочный по kick()."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        channel: Channel,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._sessionmaker = sessionmaker
        self._channel = channel
        self._clock = clock
        self._lock = asyncio.Lock()
        self._again = False
        self._tasks: set[asyncio.Task[int]] = set()

    async def run(self) -> int:
        # Один проход за раз; kick во время прохода просит пройти ещё раз
        if self._lock.locked():
            self._again = True
            return 0
        async with self._lock:
            total = 0
            while True:
                self._again = False
                try:
                    total += await dispatch_due(self._sessionmaker, self._channel, self._clock())
                except Exception:
                    # База недоступна и т.п.: следующий проход через минуту
                    logger.exception("Notification dispatch failed")
                if not self._again:
                    return total

    def kick(self) -> None:
        task = asyncio.get_running_loop().create_task(self.run())
        # Держим ссылку, иначе задачу может собрать сборщик мусора
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def register(self) -> None:
        kick_hook.register(self.kick)

    def unregister(self) -> None:
        kick_hook.register(None)
