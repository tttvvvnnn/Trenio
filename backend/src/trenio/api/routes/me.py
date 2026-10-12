from fastapi import APIRouter
from pydantic import BaseModel

from trenio.api.deps import CurrentUser, SessionDep, SettingsDep
from trenio.api.routes.trainer import TrainerOut
from trenio.services.trainers import get_active_trainer, is_admin

router = APIRouter(tags=["me"])


class MeOut(BaseModel):
    id: int
    first_name: str
    last_name: str | None
    username: str | None
    is_trainer: bool
    is_admin: bool
    # Профиль тренера, если есть доступ; onboarded_at=None значит, что нужна первая настройка
    trainer: TrainerOut | None


@router.get("/me")
async def me(user: CurrentUser, session: SessionDep, settings: SettingsDep) -> MeOut:
    trainer = await get_active_trainer(session, user.id)
    return MeOut(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        is_trainer=trainer is not None,
        is_admin=is_admin(user, settings.admin_telegram_ids),
        trainer=TrainerOut.of(trainer) if trainer is not None else None,
    )
