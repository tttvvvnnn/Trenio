from fastapi import APIRouter
from pydantic import BaseModel

from trenio.api.deps import CurrentUser, SettingsDep

router = APIRouter(tags=["me"])


class MeOut(BaseModel):
    id: int
    first_name: str
    last_name: str | None
    username: str | None
    is_trainer: bool


@router.get("/me")
async def me(user: CurrentUser, settings: SettingsDep) -> MeOut:
    return MeOut(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        is_trainer=user.telegram_id in settings.beta_trainer_ids,
    )
