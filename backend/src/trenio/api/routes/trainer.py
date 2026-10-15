from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from trenio.api.deps import CurrentTrainer, SessionDep
from trenio.db.models import Trainer
from trenio.services.trainers import InvalidTimezone, TrainerProfileUpdate, update_profile

router = APIRouter(prefix="/trainer", tags=["trainer"])


class TrainerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    display_name: str
    timezone: str
    address: str | None
    auto_confirm: bool
    cancel_hours: int
    # Шаг времени начала записи в минутах; 0 — равен длительности услуги
    slot_step_min: int
    # Запись клиента без блока: allow — можно, confirm — с подтверждением, forbid — нельзя
    one_off_mode: str
    # Правила занятий, которые клиенты подтверждают перед записью
    rules: str | None
    rules_updated_at: datetime | None
    onboarded_at: datetime | None

    @classmethod
    def of(cls, trainer: Trainer) -> "TrainerOut":
        return cls.model_validate(trainer)


class TrainerProfileIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    timezone: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=256)
    auto_confirm: bool | None = None
    # Не больше недели: дальше правило отмены теряет смысл
    cancel_hours: int | None = Field(default=None, ge=0, le=168)
    slot_step_min: Literal[0, 5, 10, 15, 20, 30, 60] | None = None
    one_off_mode: Literal["allow", "confirm", "forbid"] | None = None
    rules: str | None = Field(default=None, max_length=4000)


@router.get("/me")
async def get_profile(trainer: CurrentTrainer) -> TrainerOut:
    return TrainerOut.of(trainer)


@router.patch("/me")
async def patch_profile(
    body: TrainerProfileIn, trainer: CurrentTrainer, session: SessionDep
) -> TrainerOut:
    """Онбординг и настройки тренера: первое сохранение отмечает онбординг пройденным."""
    changes = TrainerProfileUpdate(
        display_name=body.display_name.strip() if body.display_name else None,
        timezone=body.timezone,
        address=body.address.strip() if body.address is not None else None,
        auto_confirm=body.auto_confirm,
        cancel_hours=body.cancel_hours,
        slot_step_min=body.slot_step_min,
        one_off_mode=body.one_off_mode,
        rules=body.rules.strip() if body.rules is not None else None,
    )
    try:
        trainer = await update_profile(session, trainer, changes)
    except InvalidTimezone:
        # 422, как и для остальных ошибок валидации тела запроса
        raise HTTPException(422, "Неизвестный часовой пояс") from None
    return TrainerOut.of(trainer)
