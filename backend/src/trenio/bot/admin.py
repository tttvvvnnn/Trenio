"""Команды админа: выдача и отключение доступа тренеров без правки .env и перезапуска."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject, Filter
from aiogram.types import Message

from trenio.bot.handlers import to_telegram_user
from trenio.config import get_settings
from trenio.db.models import Trainer
from trenio.db.session import get_sessionmaker
from trenio.services.admin_digest import digest_text
from trenio.services.trainers import (
    TRAINER_INVITE_PREFIX,
    create_invite,
    get_trainer_by_id,
    is_admin,
    list_trainers,
    set_trainer_active,
)
from trenio.services.users import upsert_telegram_user

# Даты в сообщениях админу показываем по Москве
ADMIN_TIMEZONE = ZoneInfo("Europe/Moscow")


class IsAdmin(Filter):
    async def __call__(self, message: Message) -> bool:
        return (
            message.from_user is not None
            and message.from_user.id in get_settings().admin_telegram_ids
        )


router = Router(name="admin")
# Для остальных пользователей этих команд просто нет
router.message.filter(IsAdmin())


def format_trainers(trainers: Sequence[Trainer]) -> str:
    if not trainers:
        return "Тренеров пока нет. Пригласите первого командой /invite."
    lines = ["Тренеры:"]
    for trainer in trainers:
        username = f" @{trainer.user.username}" if trainer.user.username else ""
        state = "активен" if trainer.is_active else "отключён"
        if trainer.is_active and trainer.onboarded_at is None:
            state += ", профиль не заполнен"
        lines.append(f"{trainer.id}. {trainer.display_name}{username} — {state}")
    lines.append("")
    lines.append("Отключить доступ: /revoke номер. Вернуть: /restore номер.")
    return "\n".join(lines)


@router.message(Command("invite"))
async def on_invite(message: Message, bot: Bot) -> None:
    assert message.from_user is not None  # гарантирует фильтр IsAdmin
    settings = get_settings()
    async with get_sessionmaker()() as session:
        admin = await upsert_telegram_user(session, to_telegram_user(message.from_user))
        invite = await create_invite(
            session, admin, timedelta(days=settings.trainer_invite_ttl_days)
        )
    me = await bot.me()
    link = f"https://t.me/{me.username}?start={TRAINER_INVITE_PREFIX}{invite.code}"
    until = invite.expires_at.astimezone(ADMIN_TIMEZONE).strftime("%d.%m.%Y %H:%M")
    await message.answer(
        "Ссылка для нового тренера. Она одноразовая и действует до "
        f"{until} МСК, перешлите её одному человеку:\n\n{link}"
    )


@router.message(Command("digest"))
async def on_digest(message: Message) -> None:
    """Та же сводка, что приходит по понедельникам, но прямо сейчас."""
    async with get_sessionmaker()() as session:
        text = await digest_text(session, datetime.now(UTC), get_settings().admin_telegram_ids)
    await message.answer(text)


@router.message(Command("trainers"))
async def on_trainers(message: Message) -> None:
    async with get_sessionmaker()() as session:
        trainers = await list_trainers(session)
    await message.answer(format_trainers(trainers))


async def _switch(message: Message, command: CommandObject, active: bool) -> None:
    name = "restore" if active else "revoke"
    if not command.args or not command.args.strip().isdigit():
        await message.answer(f"Укажите номер тренера из /trainers, например: /{name} 3")
        return
    trainer_id = int(command.args.strip())
    settings = get_settings()
    async with get_sessionmaker()() as session:
        trainer = await get_trainer_by_id(session, trainer_id)
        if trainer is None:
            await message.answer("Тренера с таким номером нет.")
            return
        if not active and is_admin(trainer.user, settings.admin_telegram_ids):
            await message.answer("Админа нельзя отключить: он тренер всегда.")
            return
        await set_trainer_active(session, trainer_id, active)
    verb = "Доступ возвращён" if active else "Доступ отключён"
    await message.answer(f"{verb}: {trainer.display_name}.")


@router.message(Command("revoke"))
async def on_revoke(message: Message, command: CommandObject) -> None:
    await _switch(message, command, active=False)


@router.message(Command("restore"))
async def on_restore(message: Message, command: CommandObject) -> None:
    await _switch(message, command, active=True)
