"""Записи и клиенты со стороны тренера."""

from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import AwareDatetime, BaseModel

from trenio.api.deps import CurrentTrainer, SessionDep
from trenio.bot.setup import get_bot_username
from trenio.db.models import Booking, TrainerClient, User
from trenio.services import bookings
from trenio.services.bookings import Actor, BookingError, BookingRejected
from trenio.services.clients import client_invite_link, list_clients
from trenio.services.users import get_user

router = APIRouter(prefix="/trainer", tags=["bookings"])

# Записи отдаём не больше чем на два месяца за один запрос
MAX_BOOKING_DAYS = 62

NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "Запись не найдена")

_ERRORS = {
    BookingError.SLOT_UNAVAILABLE: (409, "Это время уже занято. Выберите другое окошко."),
    BookingError.ALREADY_BOOKED: (409, "На это время уже есть запись."),
    BookingError.NOT_CLIENT: (403, "Сначала нужно перейти по ссылке тренера."),
    BookingError.SERVICE_NOT_FOUND: (404, "Услуга не найдена."),
    BookingError.TOO_LATE_TO_CANCEL: (409, "Отменить самому уже поздно. Напишите тренеру."),
    BookingError.STARTED: (409, "Занятие уже началось."),
    BookingError.WRONG_STATUS: (409, "Запись уже отменена или изменена."),
}


def booking_error(rejected: BookingRejected) -> HTTPException:
    code, message = _ERRORS[rejected.reason]
    return HTTPException(code, message)


class PersonOut(BaseModel):
    id: int
    first_name: str
    last_name: str | None
    username: str | None

    @classmethod
    def of(cls, user: User) -> "PersonOut":
        return cls(
            id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username,
        )


class BookingServiceOut(BaseModel):
    id: int
    name: str
    duration_min: int
    capacity: int


class BookingTrainerOut(BaseModel):
    id: int
    display_name: str
    timezone: str


class BookingOut(BaseModel):
    id: int
    status: str
    starts_at: datetime
    ends_at: datetime
    created_by: str
    cancelled_by: str | None
    service: BookingServiceOut
    trainer: BookingTrainerOut
    client: PersonOut
    # Место: адрес услуги, а если его нет — адрес тренера
    address: str | None
    # Может ли тот, кто смотрит, отменить запись прямо сейчас
    can_cancel: bool
    # До какого момента клиент отменяет сам
    cancel_deadline: datetime

    @classmethod
    def of(cls, booking: Booking, can_cancel: bool) -> "BookingOut":
        service = booking.service
        trainer = booking.trainer
        return cls(
            id=booking.id,
            status=booking.status,
            starts_at=booking.starts_at,
            ends_at=booking.ends_at,
            created_by=booking.created_by,
            cancelled_by=booking.cancelled_by,
            service=BookingServiceOut(
                id=service.id,
                name=service.name,
                duration_min=service.duration_min,
                capacity=service.capacity,
            ),
            trainer=BookingTrainerOut(
                id=trainer.id, display_name=trainer.display_name, timezone=trainer.timezone
            ),
            client=PersonOut.of(booking.client),
            address=service.address or trainer.address,
            can_cancel=can_cancel,
            cancel_deadline=bookings.client_cancel_deadline(booking),
        )


def trainer_view(booking: Booking, now: datetime) -> BookingOut:
    return BookingOut.of(booking, bookings.is_active(booking) and booking.starts_at > now)


# --- Записи ---


@router.get("/bookings")
async def list_bookings(
    trainer: CurrentTrainer,
    session: SessionDep,
    start: Annotated[date | None, Query(alias="from")] = None,
    days: Annotated[int, Query(ge=1, le=MAX_BOOKING_DAYS)] = 14,
) -> list[BookingOut]:
    """Все записи, включая отменённые, на days дней. По умолчанию с сегодняшнего дня тренера."""
    now = datetime.now(UTC)
    tz = ZoneInfo(trainer.timezone)
    if start is None:
        start = now.astimezone(tz).date()
    found = await bookings.list_trainer_bookings(
        session,
        trainer,
        datetime.combine(start, time(), tz),
        datetime.combine(start + timedelta(days=days), time(), tz),
    )
    return [trainer_view(booking, now) for booking in found]


@router.get("/bookings/pending")
async def list_pending(trainer: CurrentTrainer, session: SessionDep) -> list[BookingOut]:
    """Предстоящие записи, которые ждут подтверждения."""
    now = datetime.now(UTC)
    found = await bookings.list_pending(session, trainer, now)
    return [trainer_view(booking, now) for booking in found]


class TrainerBookingIn(BaseModel):
    client_id: int
    service_id: int
    starts_at: AwareDatetime


@router.post("/bookings", status_code=status.HTTP_201_CREATED)
async def create_booking(
    body: TrainerBookingIn, trainer: CurrentTrainer, session: SessionDep
) -> BookingOut:
    """Тренер сам записывает своего клиента в свободное окошко. Запись сразу подтверждена."""
    client = await get_user(session, body.client_id)
    if client is None:
        raise booking_error(BookingRejected(BookingError.NOT_CLIENT))
    now = datetime.now(UTC)
    try:
        booking = await bookings.create_booking(
            session,
            trainer,
            client,
            body.service_id,
            body.starts_at.astimezone(UTC),
            Actor.TRAINER,
            now,
        )
    except BookingRejected as rejected:
        raise booking_error(rejected) from None
    return trainer_view(booking, now)


async def _own_booking(session: SessionDep, trainer: CurrentTrainer, booking_id: int) -> Booking:
    try:
        return await bookings.get_trainer_booking(session, trainer, booking_id)
    except LookupError:
        raise NOT_FOUND from None


@router.post("/bookings/{booking_id}/confirm")
async def confirm_booking(
    booking_id: int, trainer: CurrentTrainer, session: SessionDep
) -> BookingOut:
    booking = await _own_booking(session, trainer, booking_id)
    try:
        booking = await bookings.confirm_booking(session, booking)
    except BookingRejected as rejected:
        raise booking_error(rejected) from None
    return trainer_view(booking, datetime.now(UTC))


@router.post("/bookings/{booking_id}/decline")
async def decline_booking(
    booking_id: int, trainer: CurrentTrainer, session: SessionDep
) -> BookingOut:
    booking = await _own_booking(session, trainer, booking_id)
    now = datetime.now(UTC)
    try:
        booking = await bookings.decline_booking(session, booking, now)
    except BookingRejected as rejected:
        raise booking_error(rejected) from None
    return trainer_view(booking, now)


@router.post("/bookings/{booking_id}/cancel")
async def cancel_booking(
    booking_id: int, trainer: CurrentTrainer, session: SessionDep
) -> BookingOut:
    booking = await _own_booking(session, trainer, booking_id)
    now = datetime.now(UTC)
    try:
        booking = await bookings.cancel_booking(session, booking, Actor.TRAINER, now)
    except BookingRejected as rejected:
        raise booking_error(rejected) from None
    return trainer_view(booking, now)


# --- Клиенты ---


class ClientOut(PersonOut):
    # Когда клиент впервые открыл ссылку тренера
    since: datetime

    @classmethod
    def of_link(cls, link: TrainerClient) -> "ClientOut":
        return cls(**PersonOut.of(link.user).model_dump(), since=link.created_at)


@router.get("/clients")
async def get_clients(trainer: CurrentTrainer, session: SessionDep) -> list[ClientOut]:
    return [ClientOut.of_link(link) for link in await list_clients(session, trainer)]


class InviteLinkOut(BaseModel):
    url: str


@router.get("/invite-link")
async def get_invite_link(trainer: CurrentTrainer) -> InviteLinkOut:
    """Персональная ссылка тренера: по ней клиент попадает к нему в бот."""
    return InviteLinkOut(url=client_invite_link(await get_bot_username(), trainer))
