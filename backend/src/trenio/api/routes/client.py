"""Запись со стороны клиента: его тренеры, их окошки и свои записи."""

from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import AwareDatetime, BaseModel

from trenio.api.deps import CurrentUser, SessionDep
from trenio.api.routes.bookings import BookingOut, CommentIn, RescheduleIn, booking_error
from trenio.api.routes.schedule import MAX_SLOT_DAYS, ServiceOut, SlotOut
from trenio.db.models import Booking, Trainer, TrainerClient, User
from trenio.services import avatars, bookings, schedule
from trenio.services.bookings import Actor, BookingRejected
from trenio.services.clients import accept_rules, get_my_link, get_my_trainer, list_my_links

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
    # Запись без блока: allow — можно, confirm — с подтверждением тренера, forbid — нельзя
    one_off_mode: str
    rules: str | None
    # Правила нужно прочитать и принять, прежде чем записываться
    rules_pending: bool
    avatar_url: str | None = None
    # Телефон клиента, который записал этот тренер; клиент может его удалить
    my_phone: str | None = None

    @classmethod
    def of(cls, link: TrainerClient) -> "ClientTrainerOut":
        trainer = link.trainer
        return cls(
            id=trainer.id,
            display_name=trainer.display_name,
            timezone=trainer.timezone,
            address=trainer.address,
            auto_confirm=trainer.auto_confirm,
            cancel_hours=trainer.cancel_hours,
            one_off_mode=trainer.one_off_mode,
            rules=trainer.rules,
            rules_pending=link.rules_pending,
            avatar_url=avatars.avatar_url(trainer.user),
            my_phone=link.phone,
        )


async def _my_link(session: SessionDep, user: User, trainer_id: int) -> TrainerClient:
    link = await get_my_link(session, user, trainer_id)
    if link is None:
        raise TRAINER_NOT_FOUND
    return link


async def _my_trainer(session: SessionDep, user: User, trainer_id: int) -> Trainer:
    trainer = await get_my_trainer(session, user, trainer_id)
    if trainer is None:
        raise TRAINER_NOT_FOUND
    return trainer


def client_view(booking: Booking, now: datetime) -> BookingOut:
    return BookingOut.of(booking, bookings.client_can_cancel(booking, now), now)


@router.get("/trainers")
async def list_trainers(user: CurrentUser, session: SessionDep) -> list[ClientTrainerOut]:
    return [ClientTrainerOut.of(link) for link in await list_my_links(session, user)]


@router.post("/trainers/{trainer_id}/rules/accept")
async def accept_trainer_rules(
    trainer_id: int, user: CurrentUser, session: SessionDep
) -> ClientTrainerOut:
    """Клиент прочитал правила тренера и согласен с ними."""
    link = await _my_link(session, user, trainer_id)
    await accept_rules(session, link, datetime.now(UTC))
    return ClientTrainerOut.of(link)


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
    reschedule: int | None = None,
) -> list[SlotOut]:
    """Свободные окошки тренера. Даты — по часовому поясу тренера.

    reschedule — своя запись, которую переносят: её нынешнее время тоже считается свободным.
    """
    trainer = await _my_trainer(session, user, trainer_id)
    if reschedule is not None:
        await _own_booking(session, user, reschedule)
    now = datetime.now(UTC)
    if start is None:
        start = now.astimezone(ZoneInfo(trainer.timezone)).date()
    slots = await schedule.trainer_slots(session, trainer, start, days, now, service_id, reschedule)
    return [SlotOut.of(slot) for slot in slots]


@router.get("/bookings")
async def list_bookings(
    user: CurrentUser,
    session: SessionDep,
    start: Annotated[date | None, Query(alias="from")] = None,
    days: Annotated[int, Query(ge=1, le=MAX_SLOT_DAYS)] = 42,
    trainer_id: int | None = None,
) -> list[BookingOut]:
    """Предстоящие записи у всех тренеров, включая отменённые и отклонённые.

    С from — все записи за days дней, в том числе прошедшие: для календаря клиента.
    Границы берём с запасом в сутки, даты по поясу тренера фронт считает сам.
    """
    now = datetime.now(UTC)
    if start is None:
        found = await bookings.list_client_bookings(session, user, now)
    else:
        found = await bookings.list_client_bookings_between(
            session,
            user,
            datetime.combine(start - timedelta(days=1), time(), UTC),
            datetime.combine(start + timedelta(days=days + 1), time(), UTC),
        )
    if trainer_id is not None:
        found = [booking for booking in found if booking.trainer_id == trainer_id]
    return [client_view(booking, now) for booking in found]


HISTORY_PAGE = 30


@router.get("/bookings/history")
async def list_history(
    user: CurrentUser,
    session: SessionDep,
    before: int | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = HISTORY_PAGE,
) -> list[BookingOut]:
    """Прошедшие, отменённые и отклонённые записи, новые сверху.

    before — id последней записи с прошлой страницы: следующая страница идёт после неё.
    """
    cursor = await _own_booking(session, user, before) if before is not None else None
    now = datetime.now(UTC)
    found = await bookings.list_client_history(session, user, now, cursor, limit)
    return [client_view(booking, now) for booking in found]


@router.get("/bookings/{booking_id:int}")
async def get_booking(booking_id: int, user: CurrentUser, session: SessionDep) -> BookingOut:
    """Одна своя запись: на неё ведёт кнопка в уведомлении."""
    booking = await _own_booking(session, user, booking_id)
    return client_view(booking, datetime.now(UTC))


class ClientBookingIn(BaseModel):
    trainer_id: int
    service_id: int
    starts_at: AwareDatetime


@router.post("/bookings", status_code=status.HTTP_201_CREATED)
async def create_booking(
    body: ClientBookingIn, user: CurrentUser, session: SessionDep
) -> BookingOut:
    """Запись в окошко. Без автоподтверждения тренера запись ждёт его решения (pending)."""
    link = await _my_link(session, user, body.trainer_id)
    if link.rules_pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "Сначала примите правила тренера")
    trainer = link.trainer
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


async def _own_booking(session: SessionDep, user: User, booking_id: int) -> Booking:
    try:
        return await bookings.get_client_booking(session, user, booking_id)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Запись не найдена") from None


@router.post("/bookings/{booking_id}/cancel")
async def cancel_booking(
    booking_id: int, user: CurrentUser, session: SessionDep, body: CommentIn | None = None
) -> BookingOut:
    booking = await _own_booking(session, user, booking_id)
    now = datetime.now(UTC)
    comment = body.comment if body else None
    try:
        booking = await bookings.cancel_booking(session, booking, Actor.CLIENT, now, comment)
    except BookingRejected as rejected:
        raise booking_error(rejected) from None
    return client_view(booking, now)


@router.post("/bookings/{booking_id}/reschedule")
async def reschedule_booking(
    booking_id: int, body: RescheduleIn, user: CurrentUser, session: SessionDep
) -> BookingOut:
    """Перенос в свободное окошко той же услуги, пока клиент ещё может отменить сам."""
    booking = await _own_booking(session, user, booking_id)
    now = datetime.now(UTC)
    try:
        booking = await bookings.reschedule_booking(
            session, booking, body.starts_at.astimezone(UTC), Actor.CLIENT, now, body.comment
        )
    except BookingRejected as rejected:
        raise booking_error(rejected) from None
    return client_view(booking, now)
