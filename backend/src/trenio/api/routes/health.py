from importlib.metadata import version

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from trenio.api.deps import SessionDep, SettingsDep

router = APIRouter(tags=["health"])


class HealthOut(BaseModel):
    status: str
    version: str
    env: str
    database: str


@router.get("/health")
async def health(session: SessionDep, settings: SettingsDep, response: Response) -> HealthOut:
    """Проверка живости для деплоя: приложение отвечает и база доступна."""
    try:
        await session.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "unavailable"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthOut(
        status="ok" if database == "ok" else "degraded",
        version=version("trenio"),
        env=settings.env,
        database=database,
    )
