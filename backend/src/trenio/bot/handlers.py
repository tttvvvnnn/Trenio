from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from aiogram.types import User as TgUser

from trenio.auth.telegram import TelegramUser
from trenio.config import get_settings
from trenio.db.models import Trainer
from trenio.db.session import get_sessionmaker
from trenio.services.trainers import (
    TRAINER_INVITE_PREFIX,
    InviteError,
    InviteRejected,
    accept_invite,
    ensure_admin_is_trainer,
)
from trenio.services.users import upsert_telegram_user

router = Router(name="start")

INVITE_ERROR_TEXT = {
    InviteError.NOT_FOUND: "Ссылка-приглашение не найдена. Попросите новую.",
    InviteError.EXPIRED: "Срок действия ссылки истёк. Попросите новую.",
    InviteError.USED: "По этой ссылке уже зарегистрировался другой тренер. Попросите новую.",
}


def webapp_keyboard(url: str) -> InlineKeyboardMarkup | None:
    # Telegram принимает кнопку Mini App только с https-адресом
    if not url.startswith("https://"):
        return None
    button = InlineKeyboardButton(text="Открыть Trenio", web_app=WebAppInfo(url=url))
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


def to_telegram_user(user: TgUser) -> TelegramUser:
    return TelegramUser(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        language_code=user.language_code,
    )


def start_text(first_name: str, trainer: Trainer | None, admin: bool) -> str:
    if trainer is None:
        return (
            f"Привет, {first_name}! Trenio помогает записываться к тренеру. "
            "Попросите у тренера ссылку-приглашение."
        )
    if trainer.onboarded_at is None:
        text = (
            f"Привет, {first_name}! У вас есть доступ тренера в Trenio. "
            "Откройте приложение и заполните профиль: имя, часовой пояс и адрес зала."
        )
    else:
        text = f"Привет, {first_name}! Расписание, услуги и клиенты живут в приложении."
    if admin:
        text += "\n\nКоманды админа: /invite — ссылка для нового тренера, /trainers — список."
    return text


@router.message(CommandStart())
async def on_start(message: Message, command: CommandObject) -> None:
    if message.from_user is None:
        return
    settings = get_settings()
    tg_user = to_telegram_user(message.from_user)
    payload = command.args or ""
    async with get_sessionmaker()() as session:
        user = await upsert_telegram_user(session, tg_user)
        if payload.startswith(TRAINER_INVITE_PREFIX):
            try:
                await accept_invite(session, user, payload.removeprefix(TRAINER_INVITE_PREFIX))
            except InviteRejected as rejected:
                await message.answer(INVITE_ERROR_TEXT[rejected.reason])
        trainer = await ensure_admin_is_trainer(session, user, settings.admin_telegram_ids)

    admin = tg_user.id in settings.admin_telegram_ids
    await message.answer(
        start_text(tg_user.first_name, trainer, admin),
        reply_markup=webapp_keyboard(settings.webapp_url),
    )
