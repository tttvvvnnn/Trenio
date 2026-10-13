"""Данные кнопок под уведомлениями. Telegram ограничивает их 64 байтами: «bk:confirm:123»."""

from enum import StrEnum

from aiogram.filters.callback_data import CallbackData


class Action(StrEnum):
    # Тренер: запись, которая ждёт подтверждения
    CONFIRM = "confirm"
    DECLINE = "decline"
    # Клиент: отменить свою запись
    CANCEL = "cancel"
    # Тренер после занятия; значения совпадают с отметками bookings.attendance
    ATTENDED = "attended"
    MISSED_CHARGED = "missed_charged"
    MISSED_FREE = "missed_free"


ATTENDANCE_ACTIONS = frozenset({Action.ATTENDED, Action.MISSED_CHARGED, Action.MISSED_FREE})


class BookingAction(CallbackData, prefix="bk"):
    action: Action
    booking_id: int
