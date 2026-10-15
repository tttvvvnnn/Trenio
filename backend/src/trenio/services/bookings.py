"""Записи на занятия: создание, подтверждение, отмена, перенос.

Защита от двойной записи. Каждая запись к тренеру идёт под блокировкой его строки
(SELECT ... FOR UPDATE), поэтому записи к одному тренеру выполняются строго по очереди.
Под блокировкой окошко пересчитывается заново, уже с учётом чужих записей: из двух
одновременных запросов на последнее место второй увидит, что мест нет.
Уникальный индекс uq_bookings_client_session страхует от повторной записи клиента.

Клиент записывается и переносит только в свободные окошки расписания. Тренер может
поставить любое будущее время: проверяем лишь, что он сам в это время не занят.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, or_, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.db.models import ACTIVE_BOOKING_STATUSES, Booking, Service, Trainer, User
from trenio.delivery.kick import kick
from trenio.services import notifications
from trenio.services.clients import is_client
from trenio.services.schedule import active_bookings, trainer_slots


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
    # Тренер в это время уже ведёт другое занятие
    TRAINER_BUSY = "trainer_busy"
    # Время в прошлом
    IN_PAST = "in_past"
    # Перенос на то же время
    SAME_TIME = "same_time"
    # Длительность группового занятия общая, у одного участника её не поменять
    GROUP_DURATION = "group_duration"


@dataclass(frozen=True)
class Terms:
    """Условия одного занятия, которые тренер задаёт при записи. None — как у услуги."""

    duration_min: int | None = None
    price: int | None = None
    # Не списывать из блока: занятие оплачивается отдельно
    no_package: bool = False


def duration_of(booking: Booking) -> timedelta:
    return booking.ends_at - booking.starts_at


# Комментарий к отмене или переносу: пара фраз, а не письмо
MAX_COMMENT_LENGTH = 500


def clean_comment(comment: str | None) -> str | None:
    """Пустой комментарий не храним: пробелы и пустая строка — это «без комментария»."""
    if comment is None:
        return None
    return comment.strip()[:MAX_COMMENT_LENGTH] or None


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
    terms: Terms | None = None,
) -> Booking:
    """Записывает клиента в окошко. Клиент записывается сам, тренер может записать его.

    Свои условия занятия (terms) ставит только тренер.
    """
    try:
        booking_id = await _create_booking(
            session, trainer, client, service_id, starts_at, actor, now, terms or Terms()
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
    kick()
    booking = await _get(session, Booking.id == booking_id)
    assert booking is not None
    return booking


async def _check_time(
    session: AsyncSession,
    trainer: Trainer,
    client_id: int,
    service: Service,
    starts_at: datetime,
    actor: Actor,
    now: datetime,
    exclude_id: int | None = None,
    duration: timedelta | None = None,
) -> None:
    """Можно ли поставить запись клиента на это время. Вызывать под блокировкой тренера.

    exclude_id — переносимая запись: она не мешает сама себе.
    duration — своя длительность занятия, если тренер поменял её; None — как у услуги.
    """
    if starts_at <= now:
        raise BookingRejected(BookingError.IN_PAST)
    standard = timedelta(minutes=service.duration_min)
    duration = duration or standard
    ends_at = starts_at + duration

    # Клиент не может быть в двух местах сразу, даже у разных тренеров
    overlap = select(Booking.id).where(
        Booking.client_id == client_id,
        Booking.status.in_(ACTIVE_BOOKING_STATUSES),
        Booking.starts_at < ends_at,
        Booking.ends_at > starts_at,
    )
    if exclude_id is not None:
        overlap = overlap.where(Booking.id != exclude_id)
    if await session.scalar(overlap) is not None:
        raise BookingRejected(BookingError.ALREADY_BOOKED)

    # Свободное окошко расписания подходит всем
    day = starts_at.astimezone(ZoneInfo(trainer.timezone)).date()
    slots = await trainer_slots(session, trainer, day, 1, now, service.id, exclude_id)
    in_slot = any(slot.starts_at == starts_at for slot in slots)
    if in_slot and duration == standard:
        return
    if actor is Actor.CLIENT and not in_slot:
        raise BookingRejected(BookingError.SLOT_UNAVAILABLE)

    # Тренер ставит и вне расписания, лишь бы сам был свободен. Групповое занятие,
    # которое уже идёт в это время, можно дополнить, пока есть места.
    # Занятие своей длительности проверяем так же: окошко считалось по длительности услуги
    busy = await active_bookings(session, trainer, starts_at, ends_at, exclude_id)
    if any(b.service_id != service.id or b.starts_at != starts_at for b in busy):
        raise BookingRejected(BookingError.TRAINER_BUSY)
    if len(busy) >= service.capacity:
        raise BookingRejected(BookingError.SLOT_UNAVAILABLE)


async def _lock_trainer(session: AsyncSession, trainer_id: int) -> None:
    # Очередь записей к тренеру: вторая транзакция ждёт здесь, пока первая не закоммитит
    await session.execute(select(Trainer.id).where(Trainer.id == trainer_id).with_for_update())


async def _create_booking(
    session: AsyncSession,
    trainer: Trainer,
    client: User,
    service_id: int,
    starts_at: datetime,
    actor: Actor,
    now: datetime,
    terms: Terms,
) -> int:
    await _lock_trainer(session, trainer.id)

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
    duration = timedelta(minutes=terms.duration_min or service.duration_min)
    if service.capacity > 1 and duration != timedelta(minutes=service.duration_min):
        raise BookingRejected(BookingError.GROUP_DURATION)
    await _check_time(session, trainer, client.id, service, starts_at, actor, now, None, duration)

    confirmed = actor is Actor.TRAINER or trainer.auto_confirm
    booking = Booking(
        trainer_id=trainer.id,
        client_id=client.id,
        service_id=service.id,
        starts_at=starts_at,
        ends_at=starts_at + duration,
        status=BookingStatus.CONFIRMED if confirmed else BookingStatus.PENDING,
        created_by=actor.value,
        price=terms.price if terms.price is not None else service.price,
        no_package=terms.no_package,
    )
    session.add(booking)
    await session.flush()
    booking_id = booking.id
    await notifications.booking_created(session, booking, now)
    await session.commit()
    return booking_id


def _check_can_change(booking: Booking, actor: Actor, now: datetime) -> None:
    """Отменить или перенести: тренер — до начала в любой момент, клиент — по правилу тренера."""
    if not is_active(booking):
        raise BookingRejected(BookingError.WRONG_STATUS)
    if booking.starts_at <= now:
        raise BookingRejected(BookingError.STARTED)
    if actor is Actor.CLIENT and not client_can_cancel(booking, now):
        raise BookingRejected(BookingError.TOO_LATE_TO_CANCEL)


async def cancel_booking(
    session: AsyncSession,
    booking: Booking,
    actor: Actor,
    now: datetime,
    comment: str | None = None,
) -> Booking:
    _check_can_change(booking, actor, now)
    booking.status = BookingStatus.CANCELLED
    booking.cancelled_by = actor.value
    booking.cancelled_at = now
    booking.cancel_comment = clean_comment(comment)
    await notifications.booking_cancelled(session, booking, notifications.Role(actor.value), now)
    await session.commit()
    kick()
    return booking


async def confirm_booking(session: AsyncSession, booking: Booking, now: datetime) -> Booking:
    if booking.status != BookingStatus.PENDING:
        raise BookingRejected(BookingError.WRONG_STATUS)
    booking.status = BookingStatus.CONFIRMED
    await notifications.booking_confirmed(session, booking, now)
    await session.commit()
    kick()
    return booking


async def decline_booking(
    session: AsyncSession, booking: Booking, now: datetime, comment: str | None = None
) -> Booking:
    if booking.status != BookingStatus.PENDING:
        raise BookingRejected(BookingError.WRONG_STATUS)
    booking.status = BookingStatus.DECLINED
    booking.cancelled_by = Actor.TRAINER.value
    booking.cancelled_at = now
    booking.cancel_comment = clean_comment(comment)
    await notifications.booking_declined(session, booking, now)
    await session.commit()
    kick()
    return booking


async def reschedule_booking(
    session: AsyncSession,
    booking: Booking,
    starts_at: datetime,
    actor: Actor,
    now: datetime,
    comment: str | None = None,
) -> Booking:
    """Перенос: та же запись получает новое время, прежнее запоминаем.

    Клиент переносит по тем же правилам, что и отменяет, и только в свободное окошко.
    Без автоподтверждения тренера перенесённая клиентом запись снова ждёт подтверждения.
    Перенос тренером сразу подтверждён.
    """
    await _lock_trainer(session, booking.trainer_id)
    try:
        # Пока ждали блокировку, запись могли отменить или уже перенести
        await session.refresh(booking)
        _check_can_change(booking, actor, now)
        if starts_at == booking.starts_at:
            raise BookingRejected(BookingError.SAME_TIME)
        await _check_time(
            session,
            booking.trainer,
            booking.client_id,
            booking.service,
            starts_at,
            actor,
            now,
            exclude_id=booking.id,
            duration=duration_of(booking),
        )
    except BookingRejected:
        await session.commit()
        raise
    previous = booking.starts_at
    duration = duration_of(booking)
    booking.starts_at = starts_at
    booking.ends_at = starts_at + duration
    confirmed = actor is Actor.TRAINER or booking.trainer.auto_confirm
    booking.status = BookingStatus.CONFIRMED if confirmed else BookingStatus.PENDING
    booking.rescheduled_from = previous
    booking.rescheduled_by = actor.value
    booking.rescheduled_at = now
    booking.reschedule_comment = clean_comment(comment)
    await notifications.booking_rescheduled(
        session, booking, notifications.Role(actor.value), previous, now
    )
    await session.commit()
    kick()
    return booking


async def change_duration(
    session: AsyncSession, booking: Booking, duration: timedelta, now: datetime
) -> None:
    """Тренер меняет длительность будущего индивидуального занятия. Коммит — за вызывающим."""
    if duration == duration_of(booking):
        return
    await _lock_trainer(session, booking.trainer_id)
    try:
        await session.refresh(booking)
        if not is_active(booking):
            raise BookingRejected(BookingError.WRONG_STATUS)
        if booking.starts_at <= now:
            raise BookingRejected(BookingError.STARTED)
        if booking.service.capacity > 1:
            raise BookingRejected(BookingError.GROUP_DURATION)
        await _check_time(
            session,
            booking.trainer,
            booking.client_id,
            booking.service,
            booking.starts_at,
            Actor.TRAINER,
            now,
            exclude_id=booking.id,
            duration=duration,
        )
    except BookingRejected:
        await session.commit()
        raise
    booking.ends_at = booking.starts_at + duration
    await notifications.booking_retimed(session, booking, now)


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


async def list_client_history(
    session: AsyncSession,
    client: User,
    now: datetime,
    before: Booking | None,
    limit: int,
) -> Sequence[Booking]:
    """История клиента у всех тренеров: прошедшие, отменённые и отклонённые записи.

    Новые сверху. before — последняя запись предыдущей страницы, следующая начинается после неё.
    """
    stmt = select(Booking).where(
        Booking.client_id == client.id,
        or_(Booking.ends_at <= now, Booking.status.not_in(ACTIVE_BOOKING_STATUSES)),
    )
    if before is not None:
        stmt = stmt.where(tuple_(Booking.starts_at, Booking.id) < (before.starts_at, before.id))
    stmt = stmt.order_by(Booking.starts_at.desc(), Booking.id.desc()).limit(limit)
    return (await session.scalars(stmt)).all()


async def list_client_bookings_between(
    session: AsyncSession, client: User, start: datetime, end: datetime
) -> Sequence[Booking]:
    """Все записи клиента у всех тренеров, которые начинаются в [start, end)."""
    stmt = (
        select(Booking)
        .where(Booking.client_id == client.id, Booking.starts_at >= start, Booking.starts_at < end)
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
