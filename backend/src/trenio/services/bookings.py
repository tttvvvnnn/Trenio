"""Записи на занятия: создание, подтверждение, отмена.

Защита от двойной записи. Каждая запись к тренеру идёт под блокировкой его строки
(SELECT ... FOR UPDATE), поэтому записи к одному тренеру выполняются строго по очереди.
Под блокировкой окошко пересчитывается заново, уже с учётом чужих записей: из двух
одновременных запросов на последнее место второй увидит, что мест нет.
Уникальный индекс uq_bookings_client_session страхует от повторной записи клиента.
"""

from collections.abc import Sequence
from datetime import datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.db.models import ACTIVE_BOOKING_STATUSES, Booking, Service, Trainer, User
from trenio.services.clients import is_client
from trenio.services.schedule import trainer_slots


class BookingStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DECLINED = "declined"
    CANCELLED = "cancelled"


class Actor(StrEnum):
    CLIENT = "client"
    TRAINER = "trainer"


class BookingError(StrEnum):
    # Окошка нет в расписании, оно уже прошло или в нём не осталось мест
    SLOT_UNAVAILABLE = "slot_unavailable"
    # У клиента уже есть запись, которая пересекается с этим временем
    ALREADY_BOOKED = "already_booked"
    NOT_CLIENT = "not_client"
    SERVICE_NOT_FOUND = "service_not_found"
    # Клиенту отменять поздно: остаётся меньше cancel_hours тренера
    TOO_LATE_TO_CANCEL = "too_late_to_cancel"
    # Занятие уже началось или прошло
    STARTED = "started"
    # Действие не подходит к статусу: например, подтвердить отменённую запись
    WRONG_STATUS = "wrong_status"


class BookingRejected(Exception):
    def __init__(self, reason: BookingError) -> None:
        super().__init__(reason)
        self.reason = reason


def is_active(booking: Booking) -> bool:
    return booking.status in ACTIVE_BOOKING_STATUSES


def client_cancel_deadline(booking: Booking) -> datetime:
    """До какого момента клиент может отменить подтверждённую запись сам."""
    return booking.starts_at - timedelta(hours=booking.trainer.cancel_hours)


def client_can_cancel(booking: Booking, now: datetime) -> bool:
    if not is_active(booking) or booking.starts_at <= now:
        return False
    # Неподтверждённую запись тренер ещё не взял в работу: её можно отменить в любой момент
    return booking.status == BookingStatus.PENDING or now <= client_cancel_deadline(booking)


async def _get(session: AsyncSession, *conditions: ColumnElement[bool]) -> Booking | None:
    # populate_existing: только что созданная запись уже в сессии, но без связанных объектов
    stmt = select(Booking).where(*conditions).execution_options(populate_existing=True)
    return await session.scalar(stmt)


async def get_client_booking(session: AsyncSession, client: User, booking_id: int) -> Booking:
    booking = await _get(session, Booking.id == booking_id, Booking.client_id == client.id)
    if booking is None:
        raise LookupError(booking_id)
    return booking


async def get_trainer_booking(session: AsyncSession, trainer: Trainer, booking_id: int) -> Booking:
    booking = await _get(session, Booking.id == booking_id, Booking.trainer_id == trainer.id)
    if booking is None:
        raise LookupError(booking_id)
    return booking


async def create_booking(
    session: AsyncSession,
    trainer: Trainer,
    client: User,
    service_id: int,
    starts_at: datetime,
    actor: Actor,
    now: datetime,
) -> Booking:
    """Записывает клиента в окошко. Клиент записывается сам, тренер может записать его."""
    try:
        booking_id = await _create_booking(
            session, trainer, client, service_id, starts_at, actor, now
        )
    except BookingRejected:
        # Изменений нет; commit снимает блокировку и, в отличие от rollback,
        # не сбрасывает загруженные объекты (expire_on_commit=False)
        await session.commit()
        raise
    except IntegrityError:
        # Сработал уникальный индекс: этот клиент уже записан на это занятие
        await session.rollback()
        raise BookingRejected(BookingError.ALREADY_BOOKED) from None
    booking = await _get(session, Booking.id == booking_id)
    assert booking is not None
    return booking


async def _create_booking(
    session: AsyncSession,
    trainer: Trainer,
    client: User,
    service_id: int,
    starts_at: datetime,
    actor: Actor,
    now: datetime,
) -> int:
    # Очередь записей к тренеру: вторая транзакция ждёт здесь, пока первая не закоммитит
    await session.execute(select(Trainer.id).where(Trainer.id == trainer.id).with_for_update())

    if not await is_client(session, trainer, client.id):
        raise BookingRejected(BookingError.NOT_CLIENT)
    service = await session.scalar(
        select(Service).where(
            Service.id == service_id,
            Service.trainer_id == trainer.id,
            Service.is_active.is_(True),
        )
    )
    if service is None:
        raise BookingRejected(BookingError.SERVICE_NOT_FOUND)
    ends_at = starts_at + timedelta(minutes=service.duration_min)

    # Клиент не может быть в двух местах сразу, даже у разных тренеров
    overlap = await session.scalar(
        select(Booking.id).where(
            Booking.client_id == client.id,
            Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            Booking.starts_at < ends_at,
            Booking.ends_at > starts_at,
        )
    )
    if overlap is not None:
        raise BookingRejected(BookingError.ALREADY_BOOKED)

    # Записаться можно только в окошко, которое сейчас свободно
    day = starts_at.astimezone(ZoneInfo(trainer.timezone)).date()
    slots = await trainer_slots(session, trainer, day, 1, now, service.id)
    if not any(slot.starts_at == starts_at for slot in slots):
        raise BookingRejected(BookingError.SLOT_UNAVAILABLE)

    confirmed = actor is Actor.TRAINER or trainer.auto_confirm
    booking = Booking(
        trainer_id=trainer.id,
        client_id=client.id,
        service_id=service.id,
        starts_at=starts_at,
        ends_at=ends_at,
        status=BookingStatus.CONFIRMED if confirmed else BookingStatus.PENDING,
        created_by=actor.value,
    )
    session.add(booking)
    await session.flush()
    booking_id = booking.id
    await session.commit()
    return booking_id


async def cancel_booking(
    session: AsyncSession, booking: Booking, actor: Actor, now: datetime
) -> Booking:
    """Отмена. Тренер отменяет до начала в любой момент, клиент — по правилу тренера."""
    if not is_active(booking):
        raise BookingRejected(BookingError.WRONG_STATUS)
    if booking.starts_at <= now:
        raise BookingRejected(BookingError.STARTED)
    if actor is Actor.CLIENT and not client_can_cancel(booking, now):
        raise BookingRejected(BookingError.TOO_LATE_TO_CANCEL)
    booking.status = BookingStatus.CANCELLED
    booking.cancelled_by = actor.value
    booking.cancelled_at = now
    await session.commit()
    return booking


async def confirm_booking(session: AsyncSession, booking: Booking) -> Booking:
    if booking.status != BookingStatus.PENDING:
        raise BookingRejected(BookingError.WRONG_STATUS)
    booking.status = BookingStatus.CONFIRMED
    await session.commit()
    return booking


async def decline_booking(session: AsyncSession, booking: Booking, now: datetime) -> Booking:
    if booking.status != BookingStatus.PENDING:
        raise BookingRejected(BookingError.WRONG_STATUS)
    booking.status = BookingStatus.DECLINED
    booking.cancelled_by = Actor.TRAINER.value
    booking.cancelled_at = now
    await session.commit()
    return booking


async def list_client_bookings(
    session: AsyncSession, client: User, now: datetime
) -> Sequence[Booking]:
    """Предстоящие записи клиента у всех тренеров, включая отменённые тренером."""
    stmt = (
        select(Booking)
        .where(Booking.client_id == client.id, Booking.ends_at > now)
        .order_by(Booking.starts_at, Booking.id)
    )
    return (await session.scalars(stmt)).all()


async def list_trainer_bookings(
    session: AsyncSession, trainer: Trainer, start: datetime, end: datetime
) -> Sequence[Booking]:
    """Все записи тренера, которые начинаются в [start, end)."""
    stmt = (
        select(Booking)
        .where(
            Booking.trainer_id == trainer.id,
            Booking.starts_at >= start,
            Booking.starts_at < end,
        )
        .order_by(Booking.starts_at, Booking.id)
    )
    return (await session.scalars(stmt)).all()


async def list_pending(session: AsyncSession, trainer: Trainer, now: datetime) -> Sequence[Booking]:
    """Предстоящие записи, которые ждут подтверждения тренера."""
    stmt = (
        select(Booking)
        .where(
            Booking.trainer_id == trainer.id,
            Booking.status == BookingStatus.PENDING,
            Booking.starts_at > now,
        )
        .order_by(Booking.starts_at, Booking.id)
    )
    return (await session.scalars(stmt)).all()
