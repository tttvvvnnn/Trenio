"""Блоки тренировок, платежи, отметки посещений и карточка клиента."""

from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Query, status
from pydantic import BaseModel, Field

from trenio.api.deps import CurrentTrainer, CurrentUser, SessionDep
from trenio.api.routes.bookings import BookingOut, ClientOut, own_booking, trainer_views
from trenio.db.models import Package, PackageTemplate
from trenio.services import packages
from trenio.services.packages import Attendance, PackageError, PackageRejected

router = APIRouter(tags=["packages"])

# Неотмеченные занятия ищем не дальше чем на два месяца назад
UNMARKED_DAYS = 62
# Сколько записей показывать в истории клиента
HISTORY_LIMIT = 100

_ERRORS = {
    PackageError.NOT_FOUND: (404, "Не найдено."),
    PackageError.NOT_CLIENT: (404, "Клиент не найден."),
    PackageError.SERVICE_NOT_FOUND: (422, "Услуга не найдена."),
    PackageError.NOT_STARTED: (409, "Отметить можно после начала занятия."),
    PackageError.WRONG_STATUS: (409, "Эту отметку нельзя поставить для такой записи."),
    PackageError.NO_SESSIONS_LEFT: (409, "В блоке не осталось занятий."),
    PackageError.PACKAGE_CLOSED: (409, "Блок закрыт."),
    PackageError.COUNT_BELOW_USED: (409, "Занятий не может быть меньше, чем уже списано."),
    PackageError.HAS_SESSIONS: (409, "Из блока уже списаны занятия. Его можно только закрыть."),
    PackageError.LINKED_TO_BOOKING: (409, "Это занятие снимается отметкой в самой записи."),
    PackageError.BAD_DATES: (422, "Срок действия не может закончиться раньше покупки."),
}


def package_error(rejected: PackageRejected) -> HTTPException:
    code, message = _ERRORS[rejected.reason]
    return HTTPException(code, message)


class ServiceRefOut(BaseModel):
    id: int
    name: str


# --- Шаблоны блоков ---


class TemplateOut(BaseModel):
    id: int
    name: str
    # null — блок подходит к любой услуге
    service: ServiceRefOut | None
    sessions_count: int
    price: int
    valid_days: int | None

    @classmethod
    def of(cls, template: PackageTemplate) -> "TemplateOut":
        service = template.service
        return cls(
            id=template.id,
            name=template.name,
            service=ServiceRefOut(id=service.id, name=service.name) if service else None,
            sessions_count=template.sessions_count,
            price=template.price,
            valid_days=template.valid_days,
        )


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    service_id: int | None = None
    sessions_count: int = Field(ge=1, le=200)
    price: int = Field(ge=0)
    valid_days: int | None = Field(default=None, ge=1, le=3650)

    def to_data(self) -> packages.TemplateData:
        return packages.TemplateData(
            name=self.name.strip(),
            service_id=self.service_id,
            sessions_count=self.sessions_count,
            price=self.price,
            valid_days=self.valid_days,
        )


@router.get("/trainer/package-templates")
async def list_templates(trainer: CurrentTrainer, session: SessionDep) -> list[TemplateOut]:
    return [TemplateOut.of(t) for t in await packages.list_templates(session, trainer)]


@router.post("/trainer/package-templates", status_code=status.HTTP_201_CREATED)
async def create_template(
    body: TemplateIn, trainer: CurrentTrainer, session: SessionDep
) -> TemplateOut:
    try:
        template = await packages.create_template(session, trainer, body.to_data())
    except PackageRejected as rejected:
        raise package_error(rejected) from None
    return TemplateOut.of(template)


@router.put("/trainer/package-templates/{template_id}")
async def replace_template(
    template_id: int, body: TemplateIn, trainer: CurrentTrainer, session: SessionDep
) -> TemplateOut:
    try:
        template = await packages.replace_template(session, trainer, template_id, body.to_data())
    except PackageRejected as rejected:
        raise package_error(rejected) from None
    return TemplateOut.of(template)


@router.delete("/trainer/package-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(template_id: int, trainer: CurrentTrainer, session: SessionDep) -> None:
    try:
        await packages.delete_template(session, trainer, template_id)
    except PackageRejected as rejected:
        raise package_error(rejected) from None


# --- Блоки ---


class PaymentOut(BaseModel):
    id: int
    amount: int
    paid_on: date
    comment: str | None


class PackageSessionOut(BaseModel):
    id: int
    # Порядковый номер в блоке, 1…N
    number: int
    day: date
    # attended — прошла, missed_charged — пропуск со списанием
    status: str
    # Запись, за которую списано; null — отмечено в блоке вручную
    booking_id: int | None


class PlannedSessionOut(BaseModel):
    """Будущая запись, которая по прогнозу спишется из блока."""

    booking_id: int
    starts_at: datetime
    # Каким по счёту занятием блока станет
    number: int


class PackageTrainerOut(BaseModel):
    id: int
    display_name: str
    timezone: str


class PackageOut(BaseModel):
    id: int
    name: str
    trainer: PackageTrainerOut
    # null — подходит к любой услуге
    service: ServiceRefOut | None
    sessions_count: int
    price: int
    purchased_on: date
    valid_until: date | None
    closed_at: datetime | None
    # active, finished (все списаны), expired (срок вышел), closed (закрыт тренером)
    status: str
    used: int
    left: int
    paid: int
    # Сколько осталось доплатить
    due: int
    # Осталось 1–2 занятия: пора предложить новый блок
    ending_soon: bool
    payments: list[PaymentOut]
    sessions: list[PackageSessionOut]
    # Неотмеченные записи, которые лягут в блок, по времени
    planned: list[PlannedSessionOut] = []

    @classmethod
    def of(
        cls, package: Package, today: date, plan: packages.Forecast | None = None
    ) -> "PackageOut":
        service = package.service
        return cls(
            id=package.id,
            name=package.name,
            trainer=PackageTrainerOut(
                id=package.trainer.id,
                display_name=package.trainer.display_name,
                timezone=package.trainer.timezone,
            ),
            service=ServiceRefOut(id=service.id, name=service.name) if service else None,
            sessions_count=package.sessions_count,
            price=package.price,
            purchased_on=package.purchased_on,
            valid_until=package.valid_until,
            closed_at=package.closed_at,
            status=packages.status(package, today),
            used=packages.used(package),
            left=packages.left(package),
            paid=packages.paid(package),
            due=packages.due(package),
            ending_soon=packages.ending_soon(package, today),
            payments=[
                PaymentOut(id=p.id, amount=p.amount, paid_on=p.paid_on, comment=p.comment)
                for p in package.payments
            ],
            sessions=[
                PackageSessionOut(
                    id=s.id, number=number, day=s.day, status=s.status, booking_id=s.booking_id
                )
                for number, s in enumerate(package.sessions, 1)
            ],
            planned=[
                PlannedSessionOut(booking_id=b.id, starts_at=b.starts_at, number=number)
                for b, number in (plan.planned_for(package) if plan else [])
            ],
        )


def _today(trainer: CurrentTrainer) -> date:
    return packages.trainer_today(trainer, datetime.now(UTC))


class PackageIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    service_id: int | None = None
    sessions_count: int = Field(ge=1, le=200)
    price: int = Field(ge=0)
    # По умолчанию — сегодня у тренера
    purchased_on: date | None = None
    valid_until: date | None = None


@router.post("/trainer/clients/{client_id}/packages", status_code=status.HTTP_201_CREATED)
async def create_package(
    client_id: int, body: PackageIn, trainer: CurrentTrainer, session: SessionDep
) -> PackageOut:
    """Продать клиенту блок. Поля шаблона фронт подставляет сам."""
    today = _today(trainer)
    data = packages.PackageData(
        name=body.name.strip(),
        service_id=body.service_id,
        sessions_count=body.sessions_count,
        price=body.price,
        purchased_on=body.purchased_on or today,
        valid_until=body.valid_until,
    )
    try:
        package = await packages.create_package(session, trainer, client_id, data)
    except PackageRejected as rejected:
        raise package_error(rejected) from None
    return PackageOut.of(package, today)


class PackagePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    sessions_count: int | None = Field(default=None, ge=1, le=200)
    price: int | None = Field(default=None, ge=0)
    purchased_on: date | None = None
    # Явный null делает блок бессрочным
    valid_until: date | None = None
    # true — закрыть досрочно, false — открыть снова
    closed: bool | None = None


@router.patch("/trainer/packages/{package_id}")
async def update_package(
    package_id: int, body: PackagePatch, trainer: CurrentTrainer, session: SessionDep
) -> PackageOut:
    changes = packages.PackageChanges(
        name=body.name.strip() if body.name else None,
        sessions_count=body.sessions_count,
        price=body.price,
        purchased_on=body.purchased_on,
        valid_until=body.valid_until,
        clear_valid_until="valid_until" in body.model_fields_set and body.valid_until is None,
        closed=body.closed,
    )
    try:
        package = await packages.update_package(
            session, trainer, package_id, changes, datetime.now(UTC)
        )
    except PackageRejected as rejected:
        raise package_error(rejected) from None
    return PackageOut.of(package, _today(trainer))


@router.delete("/trainer/packages/{package_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_package(package_id: int, trainer: CurrentTrainer, session: SessionDep) -> None:
    try:
        await packages.delete_package(session, trainer, package_id)
    except PackageRejected as rejected:
        raise package_error(rejected) from None


class PaymentIn(BaseModel):
    amount: int = Field(gt=0)
    # По умолчанию — сегодня у тренера
    paid_on: date | None = None
    comment: str | None = Field(default=None, max_length=256)


@router.post("/trainer/packages/{package_id}/payments", status_code=status.HTTP_201_CREATED)
async def add_payment(
    package_id: int, body: PaymentIn, trainer: CurrentTrainer, session: SessionDep
) -> PackageOut:
    today = _today(trainer)
    comment = body.comment.strip() if body.comment else None
    try:
        package = await packages.add_payment(
            session, trainer, package_id, body.amount, body.paid_on or today, comment or None
        )
    except PackageRejected as rejected:
        raise package_error(rejected) from None
    return PackageOut.of(package, today)


@router.delete("/trainer/packages/{package_id}/payments/{payment_id}")
async def delete_payment(
    package_id: int, payment_id: int, trainer: CurrentTrainer, session: SessionDep
) -> PackageOut:
    try:
        package = await packages.delete_payment(session, trainer, package_id, payment_id)
    except PackageRejected as rejected:
        raise package_error(rejected) from None
    return PackageOut.of(package, _today(trainer))


class ManualSessionIn(BaseModel):
    day: date
    attendance: Attendance = Attendance.ATTENDED


@router.post("/trainer/packages/{package_id}/sessions", status_code=status.HTTP_201_CREATED)
async def add_manual_session(
    package_id: int, body: ManualSessionIn, trainer: CurrentTrainer, session: SessionDep
) -> PackageOut:
    """Списать занятие, на которое не было записи в Trenio."""
    try:
        package = await packages.add_manual_session(
            session, trainer, package_id, body.day, body.attendance
        )
    except PackageRejected as rejected:
        raise package_error(rejected) from None
    return PackageOut.of(package, _today(trainer))


@router.patch("/trainer/packages/{package_id}/sessions/{session_id}")
async def update_manual_session(
    package_id: int,
    session_id: int,
    body: ManualSessionIn,
    trainer: CurrentTrainer,
    session: SessionDep,
) -> PackageOut:
    """Поменять дату или отметку занятия, списанного вручную."""
    try:
        package = await packages.update_manual_session(
            session, trainer, package_id, session_id, body.day, body.attendance
        )
    except PackageRejected as rejected:
        raise package_error(rejected) from None
    return PackageOut.of(package, _today(trainer))


@router.delete("/trainer/packages/{package_id}/sessions/{session_id}")
async def delete_manual_session(
    package_id: int, session_id: int, trainer: CurrentTrainer, session: SessionDep
) -> PackageOut:
    try:
        package = await packages.delete_manual_session(session, trainer, package_id, session_id)
    except PackageRejected as rejected:
        raise package_error(rejected) from None
    return PackageOut.of(package, _today(trainer))


# --- Отметки посещений ---


class AttendanceIn(BaseModel):
    # null снимает отметку
    attendance: Attendance | None


@router.post("/trainer/bookings/{booking_id}/attendance")
async def mark_attendance(
    booking_id: int,
    body: Annotated[AttendanceIn, Body()],
    trainer: CurrentTrainer,
    session: SessionDep,
) -> BookingOut:
    booking = await own_booking(session, trainer, booking_id)
    now = datetime.now(UTC)
    try:
        booking = await packages.mark_attendance(session, booking, body.attendance, now)
    except PackageRejected as rejected:
        raise package_error(rejected) from None
    return (await trainer_views(session, [booking], now))[0]


@router.get("/trainer/bookings/unmarked")
async def list_unmarked(
    trainer: CurrentTrainer,
    session: SessionDep,
    days: Annotated[int, Query(ge=1, le=UNMARKED_DAYS)] = UNMARKED_DAYS,
) -> list[BookingOut]:
    """Прошедшие занятия, которые тренер ещё не отметил, свежие первыми."""
    now = datetime.now(UTC)
    found = await packages.list_unmarked(session, trainer, now - timedelta(days=days), now)
    return await trainer_views(session, found, now)


# --- Карточка клиента ---


class ClientCardOut(BaseModel):
    client: ClientOut
    # Заметки тренера; клиент их не видит
    notes: str | None
    # Новые первыми
    packages: list[PackageOut]
    # Все записи у тренера, новые первыми
    history: list[BookingOut]


@router.get("/trainer/clients/{client_id}")
async def get_client_card(
    client_id: int, trainer: CurrentTrainer, session: SessionDep
) -> ClientCardOut:
    now = datetime.now(UTC)
    today = packages.trainer_today(trainer, now)
    try:
        link = await packages.get_client_link(session, trainer, client_id)
    except PackageRejected as rejected:
        raise package_error(rejected) from None
    own = await packages.list_client_packages(session, trainer, client_id)
    history = await packages.client_history(session, trainer, client_id, HISTORY_LIMIT)
    plan = await packages.forecast(session, [trainer.id], [client_id])
    summary = packages.summarize(own, today, plan, now).get(client_id)
    return ClientCardOut(
        client=ClientOut.of_link(link, summary),
        notes=link.notes,
        packages=[PackageOut.of(p, today, plan) for p in reversed(own)],
        history=await trainer_views(session, history, now),
    )


class NotesIn(BaseModel):
    notes: str | None = Field(max_length=4000)


@router.put("/trainer/clients/{client_id}/notes")
async def set_notes(
    client_id: int, body: NotesIn, trainer: CurrentTrainer, session: SessionDep
) -> NotesIn:
    notes = body.notes.strip() if body.notes else None
    try:
        await packages.set_notes(session, trainer, client_id, notes or None)
    except PackageRejected as rejected:
        raise package_error(rejected) from None
    return NotesIn(notes=notes or None)


# --- Клиент ---


@router.get("/client/packages")
async def my_packages(user: CurrentUser, session: SessionDep) -> list[PackageOut]:
    """Блоки клиента у всех тренеров, новые первыми."""
    now = datetime.now(UTC)
    found = await packages.list_my_packages(session, user.id)
    plan = await packages.forecast(session, {p.trainer_id for p in found}, [user.id])
    return [PackageOut.of(p, packages.trainer_today(p.trainer, now), plan) for p in reversed(found)]
