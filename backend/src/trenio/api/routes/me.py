from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from trenio.api.deps import CurrentUser, SessionDep, SettingsDep
from trenio.api.routes.trainer import TrainerOut
from trenio.services import notifications
from trenio.services.clients import list_my_trainers
from trenio.services.notifications import Role
from trenio.services.trainers import get_active_trainer, is_admin

router = APIRouter(tags=["me"])


class MeOut(BaseModel):
    id: int
    first_name: str
    last_name: str | None
    username: str | None
    is_trainer: bool
    is_admin: bool
    # Есть хотя бы один тренер, к которому можно записаться
    is_client: bool
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
        is_client=bool(await list_my_trainers(session, user)),
        trainer=TrainerOut.of(trainer) if trainer is not None else None,
    )


# --- Напоминания ---

# Самое раннее напоминание — за неделю, самое позднее — за 5 минут
MIN_OFFSET = 5
MAX_OFFSET = 7 * 24 * 60


class ReminderPrefsIO(BaseModel):
    enabled: bool
    # За сколько минут до начала напомнить
    offsets: Annotated[
        list[Annotated[int, Field(ge=MIN_OFFSET, le=MAX_OFFSET)]], Field(max_length=4)
    ]
    # Только у тренера: после занятия попросить отметить его
    attendance_prompt: bool = True

    @classmethod
    def of(cls, prefs: notifications.ReminderPrefs) -> "ReminderPrefsIO":
        return cls(
            enabled=prefs.enabled,
            offsets=prefs.offsets,
            attendance_prompt=prefs.attendance_prompt,
        )


class RemindersOut(BaseModel):
    # Напоминания о занятиях, на которые человек записан
    client: ReminderPrefsIO
    # Напоминания о занятиях, которые человек проводит; null — не тренер
    trainer: ReminderPrefsIO | None


@router.get("/me/reminders")
async def get_reminders(user: CurrentUser, session: SessionDep) -> RemindersOut:
    trainer = await get_active_trainer(session, user.id)
    client = await notifications.get_prefs(session, user.id, Role.CLIENT)
    own = await notifications.get_prefs(session, user.id, Role.TRAINER) if trainer else None
    return RemindersOut(
        client=ReminderPrefsIO.of(client),
        trainer=ReminderPrefsIO.of(own) if own is not None else None,
    )


@router.put("/me/reminders/{role}")
async def set_reminders(
    role: Role, body: ReminderPrefsIO, user: CurrentUser, session: SessionDep
) -> ReminderPrefsIO:
    """Сохраняет настройки роли и пересчитывает напоминания о будущих записях."""
    trainer = await get_active_trainer(session, user.id)
    if role is Role.TRAINER and trainer is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа тренера")
    prefs = notifications.ReminderPrefs(body.enabled, body.offsets, body.attendance_prompt)
    saved = await notifications.set_prefs(session, user, role, prefs, datetime.now(UTC), trainer)
    return ReminderPrefsIO.of(saved)
