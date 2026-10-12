from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from trenio.auth.telegram import TelegramUser
from trenio.config import get_settings
from trenio.db.session import get_sessionmaker
from trenio.services.users import upsert_telegram_user

router = Router(name="start")


def webapp_keyboard(url: str) -> InlineKeyboardMarkup | None:
    # Telegram принимает кнопку Mini App только с https-адресом
    if not url.startswith("https://"):
        return None
    button = InlineKeyboardButton(text="Открыть Trenio", web_app=WebAppInfo(url=url))
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


@router.message(CommandStart())
async def on_start(message: Message) -> None:
    if message.from_user is None:
        return
    settings = get_settings()
    tg_user = TelegramUser(
        id=message.from_user.id,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
        username=message.from_user.username,
        language_code=message.from_user.language_code,
    )
    async with get_sessionmaker()() as session:
        await upsert_telegram_user(session, tg_user)

    if tg_user.id in settings.beta_trainer_ids:
        text = (
            f"Привет, {tg_user.first_name}! Вы в бета-доступе для тренеров. "
            "Расписание, клиенты и блоки тренировок живут в приложении."
        )
    else:
        text = (
            f"Привет, {tg_user.first_name}! Trenio помогает записываться к тренеру. "
            "Попросите у тренера ссылку-приглашение."
        )
    await message.answer(text, reply_markup=webapp_keyboard(settings.webapp_url))
