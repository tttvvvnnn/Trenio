from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from trenio.api.deps import CurrentUser, SessionDep, SettingsDep
from trenio.api.routes.trainer import TrainerOut
from trenio.db.models import User
from trenio.services import avatars, notifications, privacy, users
from trenio.services.clients import list_my_trainers
from trenio.services.notifications import Role
from trenio.services.trainers import get_active_trainer, is_admin

router = APIRouter(tags=["me"])


class MeOut(BaseModel):
    id: int
    first_name: str
    last_name: str | None
    username: str | None
    # True — имя задано в профиле, а не взято из Telegram
    name_custom: bool
    # Адрес фото; null — фото нет, показываем инициалы
    avatar_url: str | None
    # telegram — фото из Telegram, custom — загружено своё, none — убрано
    avatar_mode: str
    is_trainer: bool
    is_admin: bool
    # Есть хотя бы один тренер, к которому можно записаться
    is_client: bool
    # Профиль тренера, если есть доступ; onboarded_at=None значит, что нужна первая настройка
    trainer: TrainerOut | None
    # Вводный тур пройден или пропущен; false — показать при входе в этот профиль
    trainer_tour_done: bool
    client_tour_done: bool
    # Нужно согласие с политикой обработки данных (впервые или после её изменения)
    consent_required: bool


@router.get("/me")
async def me(user: CurrentUser, session: SessionDep, settings: SettingsDep) -> MeOut:
    trainer = await get_active_trainer(session, user.id)
    return MeOut(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        name_custom=user.name_custom,
        avatar_url=avatars.avatar_url(user),
        avatar_mode=user.avatar_mode,
        is_trainer=trainer is not None,
        is_admin=is_admin(user, settings.admin_telegram_ids),
        is_client=bool(await list_my_trainers(session, user)),
        trainer=TrainerOut.of(trainer) if trainer is not None else None,
        trainer_tour_done=user.trainer_tour_at is not None,
        client_tour_done=user.client_tour_at is not None,
        consent_required=privacy.consent_required(user),
    )


# --- Вводный тур ---


@router.post("/me/tour/{role}", status_code=status.HTTP_204_NO_CONTENT)
async def finish_tour(role: Role, user: CurrentUser, session: SessionDep) -> None:
    """Тур пройден или пропущен: больше не показываем его сам, только из Профиля."""
    await users.finish_tour(session, user, role, datetime.now(UTC))


# --- Имя ---


class NameIn(BaseModel):
    first_name: Annotated[str, Field(min_length=1, max_length=128)]
    last_name: Annotated[str | None, Field(max_length=128)] = None


class NameOut(BaseModel):
    first_name: str
    last_name: str | None
    name_custom: bool

    @classmethod
    def of(cls, user: User) -> "NameOut":
        return cls(
            first_name=user.first_name, last_name=user.last_name, name_custom=user.name_custom
        )


@router.put("/me/name")
async def set_name(body: NameIn, user: CurrentUser, session: SessionDep) -> NameOut:
    """Своё имя, которое видят тренеры вместо имени из Telegram."""
    first_name = body.first_name.strip()
    if not first_name:
        raise HTTPException(422, "Укажите имя")
    await users.set_name(session, user, first_name, (body.last_name or "").strip() or None)
    return NameOut.of(user)


@router.delete("/me/name")
async def reset_name(user: CurrentUser, session: SessionDep) -> NameOut:
    """Вернуть имя из Telegram."""
    await users.reset_name(session, user)
    return NameOut.of(user)


# --- Фото ---


class AvatarOut(BaseModel):
    avatar_url: str | None
    avatar_mode: str

    @classmethod
    def of(cls, user: User) -> "AvatarOut":
        return cls(avatar_url=avatars.avatar_url(user), avatar_mode=user.avatar_mode)


@router.put("/me/avatar")
async def upload_avatar(request: Request, user: CurrentUser, session: SessionDep) -> AvatarOut:
    """Своё фото: тело запроса — JPEG, который Mini App уже обрезала и сжала."""
    length = int(request.headers.get("content-length") or 0)
    if length > avatars.MAX_BYTES:
        raise HTTPException(413, "Фото слишком большое")
    data = await request.body()
    if len(data) > avatars.MAX_BYTES:
        raise HTTPException(413, "Фото слишком большое")
    if not avatars.is_jpeg(data):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Нужна картинка JPEG")
    await avatars.set_custom(session, user, data)
    return AvatarOut.of(user)


@router.delete("/me/avatar")
async def remove_avatar(user: CurrentUser, session: SessionDep) -> AvatarOut:
    await avatars.remove(session, user)
    return AvatarOut.of(user)


@router.post("/me/avatar/telegram")
async def use_telegram_avatar(user: CurrentUser, session: SessionDep) -> AvatarOut:
    """Вернуть фото из Telegram; если там его нет или оно скрыто, будут инициалы."""
    await avatars.use_telegram(session, user, datetime.now(UTC))
    return AvatarOut.of(user)


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
