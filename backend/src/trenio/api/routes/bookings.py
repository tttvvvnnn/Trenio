"""Записи и клиенты со стороны тренера."""

from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.api.deps import CurrentTrainer, SessionDep
from trenio.bot.setup import get_bot_username
from trenio.db.models import Booking, TrainerClient, User
from trenio.services import avatars, bookings, clients, packages, progress
from trenio.services.bookings import Actor, BookingError, BookingRejected, BookingStatus
from trenio.services.clients import LinkError, LinkRejected, client_invite_link, list_clients
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
    BookingError.TOO_LATE_TO_CANCEL: (
        409,
        "Отменить или перенести самому уже поздно. Напишите тренеру.",
    ),
    BookingError.STARTED: (409, "Занятие уже началось."),
    BookingError.WRONG_STATUS: (409, "Запись уже отменена или изменена."),
    BookingError.TRAINER_BUSY: (409, "В это время у вас другое занятие."),
    BookingError.IN_PAST: (409, "Это время уже прошло."),
    BookingError.SAME_TIME: (409, "Запись уже стоит на это время."),
    BookingError.GROUP_DURATION: (409, "У группового занятия длительность общая для всех."),
    BookingError.ONE_OFF_FORBIDDEN: (
        409,
        "Тренер записывает только по блоку, а свободных занятий в блоке нет. "
        "Купите блок у тренера.",
    ),
}


def booking_error(rejected: BookingRejected) -> HTTPException:
    code, message = _ERRORS[rejected.reason]
    return HTTPException(code, message)


class PersonOut(BaseModel):
    id: int
    first_name: str
    last_name: str | None
    username: str | None
    # Адрес фото; null — фото нет, показываем инициалы
    avatar_url: str | None = None

    @classmethod
    def of(cls, user: User) -> "PersonOut":
        return cls(
            id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username,
            avatar_url=avatars.avatar_url(user),
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
    avatar_url: str | None = None


class BookingChargeOut(BaseModel):
    """Из какого блока списано занятие."""

    package_id: int
    package_name: str
    # Какое по счёту занятие блока, 1…sessions_count
    number: int
    sessions_count: int


class BookingOut(BaseModel):
    id: int
    status: str
    starts_at: datetime
    ends_at: datetime
    created_by: str
    cancelled_by: str | None
    # Комментарий того, кто отменил или отклонил
    cancel_comment: str | None = None
    # Последний перенос: прежнее время, кто перенёс и комментарий
    rescheduled_from: datetime | None = None
    rescheduled_by: str | None = None
    reschedule_comment: str | None = None
    service: BookingServiceOut
    trainer: BookingTrainerOut
    client: PersonOut
    # Место: адрес услуги, а если его нет — адрес тренера
    address: str | None
    # Может ли тот, кто смотрит, отменить или перенести запись прямо сейчас
    can_cancel: bool
    # До какого момента клиент отменяет сам
    cancel_deadline: datetime
    # Отметка тренера после занятия: attended, missed_charged, missed_free или null
    attendance: str | None
    # Может ли тренер отметить посещение: занятие уже началось и не отклонено
    can_mark: bool
    # Разовая: списать не из чего, оплачивается отдельно. Для неотмеченных — прогноз
    one_off: bool = False
    # Разовая у клиента, который покупал блоки: блок закончился, стоит продать новый
    out_of_block: bool = False
    charge: BookingChargeOut | None = None
    # Неотмеченная запись: из какого блока спишется, если пройдёт
    planned: BookingChargeOut | None = None
    # Только тренеру: цена занятия, если оно разовое (null — цены нет)
    price: int | None = None
    # Только тренеру: тренер решил не списывать занятие из блока
    no_package: bool = False
    # Заметка тренера к занятию. Клиенту приходит, только если она не «только для меня»
    note: str | None = None
    # Только тренеру: заметку видит только он
    note_private: bool = False

    @classmethod
    def of(
        cls,
        booking: Booking,
        can_cancel: bool,
        now: datetime,
        billing: packages.Billing | None = None,
    ) -> "BookingOut":
        service = booking.service
        trainer = booking.trainer
        return cls(
            id=booking.id,
            status=booking.status,
            starts_at=booking.starts_at,
            ends_at=booking.ends_at,
            created_by=booking.created_by,
            cancelled_by=booking.cancelled_by,
            cancel_comment=booking.cancel_comment,
            rescheduled_from=booking.rescheduled_from,
            rescheduled_by=booking.rescheduled_by,
            reschedule_comment=booking.reschedule_comment,
            service=BookingServiceOut(
                id=service.id,
                name=service.name,
                duration_min=service.duration_min,
                capacity=service.capacity,
            ),
            trainer=BookingTrainerOut(
                id=trainer.id,
                display_name=trainer.display_name,
                timezone=trainer.timezone,
                avatar_url=avatars.avatar_url(trainer.user),
            ),
            client=PersonOut.of(booking.client),
            address=service.address or trainer.address,
            can_cancel=can_cancel,
            cancel_deadline=bookings.client_cancel_deadline(booking),
            attendance=booking.attendance,
            can_mark=booking.starts_at <= now and booking.status != BookingStatus.DECLINED,
            one_off=billing is not None and booking.id in billing.one_off,
            out_of_block=billing is not None and booking.id in billing.out_of_block,
            charge=_charge_out(billing.charges.get(booking.id)) if billing else None,
            planned=_charge_out(billing.planned.get(booking.id)) if billing else None,
            note=None if booking.trainer_note_private else booking.trainer_note,
        )


def _charge_out(charge: packages.Charge | None) -> BookingChargeOut | None:
    if charge is None:
        return None
    return BookingChargeOut(
        package_id=charge.package.id,
        package_name=charge.package.name,
        number=charge.number,
        sessions_count=charge.package.sessions_count,
    )


async def trainer_views(
    session: AsyncSession, found: Sequence[Booking], now: datetime
) -> list[BookingOut]:
    """Записи глазами тренера: с отметками, разовыми и списаниями из блоков."""
    billing = await packages.billing(session, found)
    views = []
    for booking in found:
        view = BookingOut.of(booking, trainer_can_cancel(booking, now), now, billing)
        view.price = booking.price
        view.no_package = booking.no_package
        view.note = booking.trainer_note
        view.note_private = booking.trainer_note_private
        views.append(view)
    return views


def trainer_can_cancel(booking: Booking, now: datetime) -> bool:
    return bookings.is_active(booking) and booking.starts_at > now


async def trainer_view(session: AsyncSession, booking: Booking, now: datetime) -> BookingOut:
    return (await trainer_views(session, [booking], now))[0]


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
    return await trainer_views(session, found, now)


@router.get("/bookings/pending")
async def list_pending(trainer: CurrentTrainer, session: SessionDep) -> list[BookingOut]:
    """Предстоящие записи, которые ждут подтверждения."""
    now = datetime.now(UTC)
    found = await bookings.list_pending(session, trainer, now)
    return await trainer_views(session, found, now)


# Своя длительность занятия: от 5 минут до 10 часов, шагом 5 минут
Duration = Annotated[int, Field(ge=5, le=600, multiple_of=5)]
Price = Annotated[int, Field(ge=0, le=1_000_000)]


class TrainerBookingIn(BaseModel):
    client_id: int
    service_id: int
    starts_at: AwareDatetime
    # Свои условия этого занятия; пусто — как у услуги
    duration_min: Duration | None = None
    price: Price | None = None
    no_package: bool = False


class TermsIn(BaseModel):
    # Что не передано — не меняется
    duration_min: Duration | None = None
    price: Price | None = None
    no_package: bool | None = None


class CommentIn(BaseModel):
    comment: str | None = Field(default=None, max_length=bookings.MAX_COMMENT_LENGTH)


class RescheduleIn(CommentIn):
    starts_at: AwareDatetime


@router.post("/bookings", status_code=status.HTTP_201_CREATED)
async def create_booking(
    body: TrainerBookingIn, trainer: CurrentTrainer, session: SessionDep
) -> BookingOut:
    """Тренер сам записывает своего клиента на любое будущее время, когда сам свободен.

    Запись сразу подтверждена.
    """
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
            bookings.Terms(body.duration_min, body.price, body.no_package),
        )
    except BookingRejected as rejected:
        raise booking_error(rejected) from None
    return await trainer_view(session, booking, now)


async def own_booking(session: SessionDep, trainer: CurrentTrainer, booking_id: int) -> Booking:
    try:
        return await bookings.get_trainer_booking(session, trainer, booking_id)
    except LookupError:
        raise NOT_FOUND from None


@router.get("/bookings/{booking_id:int}")
async def get_booking(booking_id: int, trainer: CurrentTrainer, session: SessionDep) -> BookingOut:
    booking = await own_booking(session, trainer, booking_id)
    return await trainer_view(session, booking, datetime.now(UTC))


@router.patch("/bookings/{booking_id}/terms")
async def set_terms(
    booking_id: int, body: TermsIn, trainer: CurrentTrainer, session: SessionDep
) -> BookingOut:
    """Свои условия одного занятия: длительность, цена разового, не списывать из блока."""
    booking = await own_booking(session, trainer, booking_id)
    now = datetime.now(UTC)
    try:
        booking = await packages.set_terms(
            session,
            booking,
            packages.TermsUpdate(body.duration_min, body.price, body.no_package),
            now,
        )
    except BookingRejected as rejected:
        raise booking_error(rejected) from None
    return await trainer_view(session, booking, now)


class NoteIn(BaseModel):
    note: str | None = Field(default=None, max_length=progress.MAX_NOTE)
    # Только для тренера: клиент заметку не увидит
    private: bool = False


@router.put("/bookings/{booking_id}/note")
async def set_note(
    booking_id: int, body: NoteIn, trainer: CurrentTrainer, session: SessionDep
) -> BookingOut:
    """Заметка к занятию: что делали, как прошло."""
    booking = await own_booking(session, trainer, booking_id)
    booking = await progress.set_note(session, booking, body.note, body.private)
    return await trainer_view(session, booking, datetime.now(UTC))


@router.post("/bookings/{booking_id}/confirm")
async def confirm_booking(
    booking_id: int, trainer: CurrentTrainer, session: SessionDep
) -> BookingOut:
    booking = await own_booking(session, trainer, booking_id)
    now = datetime.now(UTC)
    try:
        booking = await bookings.confirm_booking(session, booking, now)
    except BookingRejected as rejected:
        raise booking_error(rejected) from None
    return await trainer_view(session, booking, now)


@router.post("/bookings/{booking_id}/decline")
async def decline_booking(
    booking_id: int, trainer: CurrentTrainer, session: SessionDep, body: CommentIn | None = None
) -> BookingOut:
    booking = await own_booking(session, trainer, booking_id)
    now = datetime.now(UTC)
    comment = body.comment if body else None
    try:
        booking = await bookings.decline_booking(session, booking, now, comment)
    except BookingRejected as rejected:
        raise booking_error(rejected) from None
    return await trainer_view(session, booking, now)


@router.post("/bookings/{booking_id}/cancel")
async def cancel_booking(
    booking_id: int, trainer: CurrentTrainer, session: SessionDep, body: CommentIn | None = None
) -> BookingOut:
    booking = await own_booking(session, trainer, booking_id)
    now = datetime.now(UTC)
    comment = body.comment if body else None
    try:
        booking = await bookings.cancel_booking(session, booking, Actor.TRAINER, now, comment)
    except BookingRejected as rejected:
        raise booking_error(rejected) from None
    return await trainer_view(session, booking, now)


@router.post("/bookings/{booking_id}/reschedule")
async def reschedule_booking(
    booking_id: int, body: RescheduleIn, trainer: CurrentTrainer, session: SessionDep
) -> BookingOut:
    """Перенос на любое будущее время, когда тренер свободен. Запись сразу подтверждена."""
    booking = await own_booking(session, trainer, booking_id)
    now = datetime.now(UTC)
    try:
        booking = await bookings.reschedule_booking(
            session, booking, body.starts_at.astimezone(UTC), Actor.TRAINER, now, body.comment
        )
    except BookingRejected as rejected:
        raise booking_error(rejected) from None
    return await trainer_view(session, booking, now)


# --- Клиенты ---


class ClientBlockOut(BaseModel):
    name: str
    used: int
    sessions_count: int


class ClientOut(PersonOut):
    # Когда клиент впервые открыл ссылку тренера
    since: datetime
    # Сколько занятий осталось в действующих блоках; null — действующих блоков нет
    sessions_left: int | None = None
    # Сколько клиент должен доплатить по блокам
    debt: int = 0
    # Покупал ли клиент блоки вообще: отличает «блок закончился» от «блоков не было»
    has_packages: bool = False
    # Сколько будущих записей не покрыто блоками: они будут разовыми
    upcoming_one_off: int = 0
    # Клиент без Telegram, которого тренер завёл сам: имя правит тренер, уведомлений нет
    offline: bool = False
    # Клиент удалил аккаунт: осталась обезличенная история, записать его нельзя
    deleted: bool = False
    # Блок, из которого сейчас списываются занятия
    block: ClientBlockOut | None = None
    # Блок кончается: пора предложить новый
    ending_soon: bool = False

    @classmethod
    def of_link(
        cls, link: TrainerClient, summary: packages.ClientSummary | None = None
    ) -> "ClientOut":
        out = cls(
            **PersonOut.of(link.user).model_dump(),
            since=link.created_at,
            offline=link.user.is_offline and not link.user.is_deleted,
            deleted=link.user.is_deleted,
        )
        if summary is not None:
            out.sessions_left = summary.sessions_left
            out.debt = summary.debt
            out.has_packages = summary.has_packages
            out.upcoming_one_off = summary.upcoming_one_off
            out.ending_soon = summary.ending_soon
            if summary.current is not None:
                out.block = ClientBlockOut(
                    name=summary.current.name,
                    used=packages.used(summary.current),
                    sessions_count=summary.current.sessions_count,
                )
        return out


@router.get("/clients")
async def get_clients(trainer: CurrentTrainer, session: SessionDep) -> list[ClientOut]:
    now = datetime.now(UTC)
    today = packages.trainer_today(trainer, now)
    summary = packages.summarize(
        await packages.list_trainer_packages(session, trainer),
        today,
        await packages.forecast(session, [trainer.id]),
        now,
    )
    return [
        ClientOut.of_link(link, summary.get(link.user_id))
        for link in await list_clients(session, trainer)
    ]


class InviteLinkOut(BaseModel):
    url: str


@router.get("/invite-link")
async def get_invite_link(trainer: CurrentTrainer) -> InviteLinkOut:
    """Персональная ссылка тренера: по ней клиент попадает к нему в бот."""
    return InviteLinkOut(url=client_invite_link(await get_bot_username(), trainer))


# --- Клиенты без Telegram ---

_LINK_ERRORS = {
    LinkError.NOT_FOUND: (404, "Клиент не найден."),
    LinkError.NOT_OFFLINE: (409, "Клиент уже пользуется Telegram."),
    LinkError.TARGET_OFFLINE: (409, "Объединить можно только с клиентом из Telegram."),
    LinkError.OWN_LINK: (409, "Это ваш собственный аккаунт."),
}


def link_error(rejected: LinkRejected) -> HTTPException:
    code, message = _LINK_ERRORS[rejected.reason]
    return HTTPException(code, message)


class ClientNameIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=128)
    last_name: str | None = Field(default=None, max_length=128)


class NewClientIn(ClientNameIn):
    notes: str | None = Field(default=None, max_length=4000)


def _clean(value: str | None) -> str | None:
    return value.strip() or None if value else None


@router.post("/clients", status_code=status.HTTP_201_CREATED)
async def create_client(
    body: NewClientIn, trainer: CurrentTrainer, session: SessionDep
) -> ClientOut:
    """Тренер заводит клиента, который не будет пользоваться ботом."""
    first_name = body.first_name.strip()
    if not first_name:
        raise HTTPException(422, "Укажите имя")
    link = await clients.create_offline_client(
        session, trainer, first_name, _clean(body.last_name), _clean(body.notes)
    )
    return ClientOut.of_link(link)


@router.patch("/clients/{client_id}")
async def rename_client(
    client_id: int, body: ClientNameIn, trainer: CurrentTrainer, session: SessionDep
) -> ClientOut:
    first_name = body.first_name.strip()
    if not first_name:
        raise HTTPException(422, "Укажите имя")
    try:
        link = await clients.rename_offline_client(
            session, trainer, client_id, first_name, _clean(body.last_name)
        )
    except LinkRejected as rejected:
        raise link_error(rejected) from None
    return ClientOut.of_link(link)


@router.post("/clients/{client_id}/claim-link")
async def get_claim_link(
    client_id: int, trainer: CurrentTrainer, session: SessionDep
) -> InviteLinkOut:
    """Личная ссылка для клиента без Telegram: открыв её, он заберёт свою историю."""
    try:
        code = await clients.claim_code(session, trainer, client_id)
    except LinkRejected as rejected:
        raise link_error(rejected) from None
    return InviteLinkOut(url=clients.claim_link(await get_bot_username(), code))


class MergeIn(BaseModel):
    # Клиент с Telegram, который на самом деле тот же человек
    into_id: int


@router.post("/clients/{client_id}/merge", status_code=status.HTTP_204_NO_CONTENT)
async def merge_client(
    client_id: int, body: MergeIn, trainer: CurrentTrainer, session: SessionDep
) -> None:
    try:
        await clients.merge_offline_client(
            session, trainer, client_id, body.into_id, datetime.now(UTC)
        )
    except LinkRejected as rejected:
        raise link_error(rejected) from None
