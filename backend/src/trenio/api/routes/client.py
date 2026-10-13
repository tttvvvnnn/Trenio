"""Запись со стороны клиента: его тренеры, их окошки и свои записи."""

from datetime import UTC, date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import AwareDatetime, BaseModel

from trenio.api.deps import CurrentUser, SessionDep
from trenio.api.routes.bookings import BookingOut, booking_error
from trenio.api.routes.schedule import MAX_SLOT_DAYS, ServiceOut, SlotOut
from trenio.db.models import Booking, Trainer, User
from trenio.services import bookings, schedule
from trenio.services.bookings import Actor, BookingRejected
from trenio.services.clients import get_my_trainer, list_my_trainers

router = APIRouter(prefix="/client", tags=["client"])

TRAINER_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "Тренер не найден")


class ClientTrainerOut(BaseModel):
    """Что клиент видит о тренере."""

    id: int
    display_name: str
    timezone: str
    address: str | None
    auto_confirm: bool
    cancel_hours: int

    @classmethod
    def of(cls, trainer: Trainer) -> "ClientTrainerOut":
        return cls(
            id=trainer.id,
            display_name=trainer.display_name,
            timezone=trainer.timezone,
            address=trainer.address,
            auto_confirm=trainer.auto_confirm,
            cancel_hours=trainer.cancel_hours,
        )


async def _my_trainer(session: SessionDep, user: User, trainer_id: int) -> Trainer:
    trainer = await get_my_trainer(session, user, trainer_id)
    if trainer is None:
        raise TRAINER_NOT_FOUND
    return trainer


def client_view(booking: Booking, now: datetime) -> BookingOut:
    return BookingOut.of(booking, bookings.client_can_cancel(booking, now))


@router.get("/trainers")
async def list_trainers(user: CurrentUser, session: SessionDep) -> list[ClientTrainerOut]:
    return [ClientTrainerOut.of(trainer) for trainer in await list_my_trainers(session, user)]


@router.get("/trainers/{trainer_id}/services")
async def list_services(
    trainer_id: int, user: CurrentUser, session: SessionDep
) -> list[ServiceOut]:
    trainer = await _my_trainer(session, user, trainer_id)
    services = await schedule.list_services(session, trainer)
    return [ServiceOut.model_validate(service) for service in services]


@router.get("/trainers/{trainer_id}/slots")
async def list_slots(
    trainer_id: int,
    user: CurrentUser,
    session: SessionDep,
    start: Annotated[date | None, Query(alias="from")] = None,
    days: Annotated[int, Query(ge=1, le=MAX_SLOT_DAYS)] = 14,
    service_id: int | None = None,
) -> list[SlotOut]:
    """Свободные окошки тренера. Даты — по часовому поясу тренера."""
    trainer = await _my_trainer(session, user, trainer_id)
    now = datetime.now(UTC)
    if start is None:
        start = now.astimezone(ZoneInfo(trainer.timezone)).date()
    slots = await schedule.trainer_slots(session, trainer, start, days, now, service_id)
    return [SlotOut.of(slot) for slot in slots]


@router.get("/bookings")
async def list_bookings(user: CurrentUser, session: SessionDep) -> list[BookingOut]:
    """Предстоящие записи у всех тренеров, включая отменённые и отклонённые."""
    now = datetime.now(UTC)
    found = await bookings.list_client_bookings(session, user, now)
    return [client_view(booking, now) for booking in found]


class ClientBookingIn(BaseModel):
    trainer_id: int
    service_id: int
    starts_at: AwareDatetime


@router.post("/bookings", status_code=status.HTTP_201_CREATED)
async def create_booking(
    body: ClientBookingIn, user: CurrentUser, session: SessionDep
) -> BookingOut:
    """Запись в окошко. Без автоподтверждения тренера запись ждёт его решения (pending)."""
    trainer = await _my_trainer(session, user, body.trainer_id)
    now = datetime.now(UTC)
    try:
        booking = await bookings.create_booking(
            session,
            trainer,
            user,
            body.service_id,
            body.starts_at.astimezone(UTC),
            Actor.CLIENT,
            now,
        )
    except BookingRejected as rejected:
        raise booking_error(rejected) from None
    return client_view(booking, now)


@router.post("/bookings/{booking_id}/cancel")
async def cancel_booking(booking_id: int, user: CurrentUser, session: SessionDep) -> BookingOut:
    try:
        booking = await bookings.get_client_booking(session, user, booking_id)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Запись не найдена") from None
    now = datetime.now(UTC)
    try:
        booking = await bookings.cancel_booking(session, booking, Actor.CLIENT, now)
    except BookingRejected as rejected:
        raise booking_error(rejected) from None
    return client_view(booking, now)
