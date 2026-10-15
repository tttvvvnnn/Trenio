import logging
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from trenio.db.session import get_sessionmaker
from trenio.delivery.channel import TelegramChannel
from trenio.delivery.sender import Sender
from trenio.services.packages import schedule_expiry_alerts

logger = logging.getLogger(__name__)

# Как часто отправщик проверяет очередь уведомлений
DISPATCH_INTERVAL_SECONDS = 60
# Как часто ставим предупреждения о сроке блоков: повторы отсекает dedup_key
EXPIRY_INTERVAL_SECONDS = 60 * 60


async def plan_expiry_alerts() -> None:
    try:
        async with get_sessionmaker()() as session:
            await schedule_expiry_alerts(session, datetime.now(UTC))
    except Exception:
        logger.exception("Package expiry planning failed")


def create_scheduler() -> tuple[AsyncIOScheduler, Sender]:
    """Планировщик с отправкой уведомлений раз в минуту.

    Уведомления забираются из таблицы через SELECT ... FOR UPDATE SKIP LOCKED, поэтому
    планировщик можно вынести в отдельный контейнер или запустить в двух экземплярах.
    """
    sender = Sender(get_sessionmaker(), TelegramChannel())
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        sender.run,
        "interval",
        seconds=DISPATCH_INTERVAL_SECONDS,
        id="dispatch_notifications",
        # Первый проход сразу при старте: забрать то, что накопилось, пока сервис лежал
        next_run_time=datetime.now(UTC),
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        plan_expiry_alerts,
        "interval",
        seconds=EXPIRY_INTERVAL_SECONDS,
        id="plan_expiry_alerts",
        next_run_time=datetime.now(UTC),
        max_instances=1,
        coalesce=True,
    )
    return scheduler, sender
