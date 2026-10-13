"""Кнопки под уведомлениями: подтвердить, отклонить, отменить, отметить занятие.

Кнопка делает то же, что Mini App, через те же сервисы и с теми же правилами. Права
проверяются заново по тому, кто нажал: чужую запись кнопкой не тронуть, даже подделав данные.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from aiogram import F, Router
from aiogram.types import CallbackQuery, InaccessibleMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.bot.callbacks import ATTENDANCE_ACTIONS, Action, BookingAction
from trenio.db.models import User
from trenio.db.session import get_sessionmaker
from trenio.delivery.channel import to_markup
from trenio.delivery.texts import open_app
from trenio.services import bookings, packages
from trenio.services.bookings import Actor, BookingError, BookingRejected
from trenio.services.packages import Attendance, PackageError, PackageRejected
from trenio.services.trainers import get_active_trainer

router = Router(name="actions")

DONE_TEXT = {
    Action.CONFIRM: "✓ Подтверждено",
    Action.DECLINE: "✗ Отклонено",
    Action.CANCEL: "✗ Запись отменена",
    Action.ATTENDED: "✓ Отмечено: прошла",
    Action.MISSED_CHARGED: "✓ Отмечено: пропуск, списано",
    Action.MISSED_FREE: "✓ Отмечено: пропуск, не списано",
}

BOOKING_ERROR_TEXT = {
    BookingError.TOO_LATE_TO_CANCEL: "Отменить самому уже поздно. Напишите тренеру.",
    BookingError.STARTED: "Занятие уже началось.",
    BookingError.WRONG_STATUS: "Запись уже отменена или изменена в приложении.",
}

PACKAGE_ERROR_TEXT = {
    PackageError.NOT_STARTED: "Отметить можно после начала занятия.",
    PackageError.WRONG_STATUS: "Эту отметку нельзя поставить для такой записи.",
}

NOT_FOUND_TEXT = "Запись не найдена."


@dataclass(frozen=True)
class Outcome:
    ok: bool
    text: str


async def apply_action(
    session: AsyncSession, telegram_id: int, data: BookingAction, now: datetime
) -> Outcome:
    """Выполняет нажатую кнопку от имени того, кто её нажал."""
    user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None:
        return Outcome(False, NOT_FOUND_TEXT)
    try:
        if data.action is Action.CANCEL:
            booking = await bookings.get_client_booking(session, user, data.booking_id)
            await bookings.cancel_booking(session, booking, Actor.CLIENT, now)
        else:
            trainer = await get_active_trainer(session, user.id)
            if trainer is None:
                return Outcome(False, NOT_FOUND_TEXT)
            booking = await bookings.get_trainer_booking(session, trainer, data.booking_id)
            if data.action is Action.CONFIRM:
                await bookings.confirm_booking(session, booking, now)
            elif data.action is Action.DECLINE:
                await bookings.decline_booking(session, booking, now)
            else:
                assert data.action in ATTENDANCE_ACTIONS
                await packages.mark_attendance(session, booking, Attendance(data.action), now)
    except LookupError:
        return Outcome(False, NOT_FOUND_TEXT)
    except BookingRejected as rejected:
        return Outcome(False, BOOKING_ERROR_TEXT.get(rejected.reason, "Не получилось."))
    except PackageRejected as rejected:
        return Outcome(False, PACKAGE_ERROR_TEXT.get(rejected.reason, "Не получилось."))
    return Outcome(True, DONE_TEXT[data.action])


@router.callback_query(BookingAction.filter())
async def on_action(query: CallbackQuery, callback_data: BookingAction) -> None:
    async with get_sessionmaker()() as session:
        outcome = await apply_action(session, query.from_user.id, callback_data, datetime.now(UTC))
    message = query.message
    if not outcome.ok:
        await query.answer(outcome.text, show_alert=True)
        return
    await query.answer(outcome.text)
    # Итог дописываем в само уведомление и убираем кнопки действий, чтобы не нажать дважды
    if message is not None and not isinstance(message, InaccessibleMessage) and message.text:
        await message.edit_text(
            f"{message.text}\n\n{outcome.text}", reply_markup=to_markup(open_app())
        )


# Кнопки старых версий бота, которых больше нет, просто гасим
@router.callback_query(F.data)
async def on_unknown(query: CallbackQuery) -> None:
    await query.answer()
