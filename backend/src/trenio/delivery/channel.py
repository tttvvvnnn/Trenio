"""Каналы доставки. Сейчас один — Telegram; потом рядом встанет push мобильного приложения."""

from dataclasses import dataclass, field
from typing import Protocol

from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramNotFound,
    TelegramRetryAfter,
)
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from trenio.db.models import User


@dataclass(frozen=True)
class Button:
    text: str
    # Ровно одно из двух: действие в боте или открыть Mini App
    callback_data: str | None = None
    webapp_url: str | None = None


@dataclass(frozen=True)
class OutMessage:
    text: str
    # Ряды кнопок под сообщением
    buttons: list[list[Button]] = field(default_factory=list)


class DeliveryError(Exception):
    def __init__(self, message: str, permanent: bool) -> None:
        super().__init__(message)
        # permanent: повторять бесполезно (человек заблокировал бота, чата нет)
        self.permanent = permanent


class Channel(Protocol):
    async def send(self, user: User, message: OutMessage) -> None:
        """Отправляет сообщение или бросает DeliveryError."""


def to_markup(buttons: list[list[Button]]) -> InlineKeyboardMarkup | None:
    rows = [
        [
            InlineKeyboardButton(
                text=button.text,
                callback_data=button.callback_data,
                web_app=WebAppInfo(url=button.webapp_url) if button.webapp_url else None,
            )
            for button in row
        ]
        for row in buttons
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


class TelegramChannel:
    async def send(self, user: User, message: OutMessage) -> None:
        from trenio.bot.setup import get_bot

        if user.telegram_id is None:
            raise DeliveryError("no telegram_id", permanent=True)
        try:
            await get_bot().send_message(
                user.telegram_id, message.text, reply_markup=to_markup(message.buttons)
            )
        except (TelegramForbiddenError, TelegramNotFound) as error:
            # Заблокировал бота или удалил аккаунт
            raise DeliveryError(str(error), permanent=True) from error
        except TelegramBadRequest as error:
            # «chat not found» и ошибки в самом сообщении повтором не исправить
            raise DeliveryError(str(error), permanent=True) from error
        except (TelegramRetryAfter, TelegramNetworkError) as error:
            raise DeliveryError(str(error), permanent=False) from error
        except TelegramAPIError as error:
            raise DeliveryError(str(error), permanent=False) from error
