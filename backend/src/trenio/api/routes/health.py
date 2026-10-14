from datetime import UTC, datetime, timedelta
from importlib.metadata import version

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import func, select, text

from trenio.api.deps import SessionDep, SettingsDep
from trenio.db.models import Notification

router = APIRouter(tags=["health"])

# Отправщик проходит очередь раз в минуту. Если уведомление ждёт дольше,
# значит планировщик не работает: напоминания перестали уходить
NOTIFICATIONS_LAG_LIMIT = timedelta(minutes=10)


class HealthOut(BaseModel):
    status: str
    version: str
    env: str
    database: str
    # ok — очередь уведомлений движется, stuck — есть просроченные, unknown — база недоступна
    notifications: str


@router.get("/health")
async def health(session: SessionDep, settings: SettingsDep, response: Response) -> HealthOut:
    """Проверка живости для деплоя и мониторинга: приложение отвечает и база доступна.

    notifications не влияет на status и код ответа: деплой ждёт только живости,
    а застрявшую очередь ловит отдельный монитор по слову "notifications":"ok".
    """
    notifications = "unknown"
    try:
        await session.execute(text("SELECT 1"))
        database = "ok"
        overdue = await session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.status == "pending",
                Notification.send_at < datetime.now(UTC) - NOTIFICATIONS_LAG_LIMIT,
            )
        )
        notifications = "stuck" if overdue else "ok"
    except Exception:
        database = "unavailable"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthOut(
        status="ok" if database == "ok" else "degraded",
        version=version("trenio"),
        env=settings.env,
        database=database,
        notifications=notifications,
    )
