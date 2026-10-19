import logging
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from trenio.config import get_settings
from trenio.db.session import get_sessionmaker
from trenio.delivery.channel import TelegramChannel
from trenio.delivery.sender import Sender
from trenio.services.admin_digest import digest_text
from trenio.services.packages import schedule_expiry_alerts
from trenio.services.subscription import schedule_ending_alerts

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


async def send_admin_digest() -> None:
    """Недельная сводка админам. Только на prod: с dev пришла бы вторая такая же."""
    settings = get_settings()
    if settings.env != "prod" or not settings.admin_telegram_ids:
        return
    from trenio.bot.setup import get_bot

    try:
        async with get_sessionmaker()() as session:
            text = await digest_text(session, datetime.now(UTC), settings.admin_telegram_ids)
        for chat_id in settings.admin_telegram_ids:
            try:
                await get_bot().send_message(chat_id, text)
            except Exception:
                logger.exception("Admin digest to %s failed", chat_id)
    except Exception:
        logger.exception("Admin digest failed")


async def plan_subscription_alerts() -> None:
    try:
        async with get_sessionmaker()() as session:
            await schedule_ending_alerts(session, datetime.now(UTC))
    except Exception:
        logger.exception("Subscription alerts planning failed")


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
    scheduler.add_job(
        send_admin_digest,
        "cron",
        day_of_week="mon",
        hour=9,
        timezone="Europe/Moscow",
        id="send_admin_digest",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        plan_subscription_alerts,
        "interval",
        seconds=EXPIRY_INTERVAL_SECONDS,
        id="plan_subscription_alerts",
        next_run_time=datetime.now(UTC),
        max_instances=1,
        coalesce=True,
    )
    return scheduler, sender
