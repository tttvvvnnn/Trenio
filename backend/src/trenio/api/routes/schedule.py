"""Услуги, недельный шаблон, исключения и окошки тренера."""

from datetime import UTC, date, datetime, time
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from trenio.api.deps import CurrentTrainer, SessionDep
from trenio.db.models import ScheduleException, ScheduleRule
from trenio.services import schedule
from trenio.services.slots import ExceptionKind

router = APIRouter(prefix="/trainer", tags=["schedule"])

# Окошки отдаём не дальше месяца вперёд за один запрос
MAX_SLOT_DAYS = 31

NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "Не найдено")


def _bad_request(error: schedule.ScheduleError) -> HTTPException:
    return HTTPException(422, str(error))


def _trim(value: time) -> time:
    # Секунды в расписании не нужны, а 10:00:30 дало бы странные окошки
    return value.replace(second=0, microsecond=0, tzinfo=None)


# --- Услуги ---


class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    duration_min: int
    capacity: int
    price: int | None
    address: str | None
    is_active: bool


class ServiceIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    duration_min: int = Field(ge=5, le=600)
    capacity: int = Field(default=1, ge=1, le=100)
    price: int | None = Field(default=None, ge=0)
    address: str | None = Field(default=None, max_length=256)


class ServicePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    duration_min: int | None = Field(default=None, ge=5, le=600)
    capacity: int | None = Field(default=None, ge=1, le=100)
    price: int | None = Field(default=None, ge=0)
    address: str | None = Field(default=None, max_length=256)
    is_active: bool | None = None


@router.get("/services")
async def list_services(
    trainer: CurrentTrainer, session: SessionDep, include_inactive: bool = False
) -> list[ServiceOut]:
    services = await schedule.list_services(session, trainer, include_inactive)
    return [ServiceOut.model_validate(service) for service in services]


@router.post("/services", status_code=status.HTTP_201_CREATED)
async def create_service(
    body: ServiceIn, trainer: CurrentTrainer, session: SessionDep
) -> ServiceOut:
    data = schedule.ServiceData(
        name=body.name.strip(),
        duration_min=body.duration_min,
        capacity=body.capacity,
        price=body.price,
        address=body.address.strip() if body.address else None,
    )
    return ServiceOut.model_validate(await schedule.create_service(session, trainer, data))


@router.patch("/services/{service_id}")
async def update_service(
    service_id: int, body: ServicePatch, trainer: CurrentTrainer, session: SessionDep
) -> ServiceOut:
    changes = schedule.ServiceChanges(
        name=body.name.strip() if body.name else None,
        duration_min=body.duration_min,
        capacity=body.capacity,
        price=body.price,
        # Явный null в теле запроса убирает цену
        clear_price="price" in body.model_fields_set and body.price is None,
        address=body.address.strip() if body.address is not None else None,
        is_active=body.is_active,
    )
    try:
        service = await schedule.update_service(session, trainer, service_id, changes)
    except schedule.NotFound:
        raise NOT_FOUND from None
    return ServiceOut.model_validate(service)


# --- Недельный шаблон ---


class RuleOut(BaseModel):
    id: int
    weekday: int
    start: time
    end: time
    service_ids: list[int]

    @classmethod
    def of(cls, rule: ScheduleRule) -> "RuleOut":
        return cls(
            id=rule.id,
            weekday=rule.weekday,
            start=rule.start_time,
            end=rule.end_time,
            service_ids=[service.id for service in rule.services],
        )


class RuleIn(BaseModel):
    weekday: int = Field(ge=0, le=6, description="0 — понедельник, 6 — воскресенье")
    start: time
    end: time
    service_ids: list[int] = Field(
        default_factory=list, description="Пустой список — все активные услуги"
    )

    _trim_times = field_validator("start", "end")(_trim)

    def to_data(self) -> schedule.RuleData:
        return schedule.RuleData(self.weekday, self.start, self.end, self.service_ids)


@router.get("/schedule/rules")
async def list_rules(trainer: CurrentTrainer, session: SessionDep) -> list[RuleOut]:
    return [RuleOut.of(rule) for rule in await schedule.list_rules(session, trainer)]


@router.post("/schedule/rules", status_code=status.HTTP_201_CREATED)
async def create_rule(body: RuleIn, trainer: CurrentTrainer, session: SessionDep) -> RuleOut:
    try:
        rule = await schedule.create_rule(session, trainer, body.to_data())
    except schedule.ScheduleError as error:
        raise _bad_request(error) from None
    except schedule.NotFound:
        raise HTTPException(422, "Услуга не найдена") from None
    return RuleOut.of(rule)


@router.put("/schedule/rules/{rule_id}")
async def replace_rule(
    rule_id: int, body: RuleIn, trainer: CurrentTrainer, session: SessionDep
) -> RuleOut:
    try:
        rule = await schedule.replace_rule(session, trainer, rule_id, body.to_data())
    except schedule.ScheduleError as error:
        raise _bad_request(error) from None
    except schedule.NotFound:
        raise NOT_FOUND from None
    return RuleOut.of(rule)


@router.delete("/schedule/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: int, trainer: CurrentTrainer, session: SessionDep) -> None:
    try:
        await schedule.delete_rule(session, trainer, rule_id)
    except schedule.NotFound:
        raise NOT_FOUND from None


# --- Исключения ---


class ExceptionOut(BaseModel):
    id: int
    day: date
    kind: ExceptionKind
    start: time | None
    end: time | None

    @classmethod
    def of(cls, exc: ScheduleException) -> "ExceptionOut":
        return cls(
            id=exc.id,
            day=exc.day,
            kind=ExceptionKind(exc.kind),
            start=exc.start_time,
            end=exc.end_time,
        )


class ExceptionIn(BaseModel):
    day: date
    kind: ExceptionKind
    # Для выходного на весь день время не указывают
    start: time | None = None
    end: time | None = None

    @field_validator("start", "end")
    @classmethod
    def _trim_optional(cls, value: time | None) -> time | None:
        return _trim(value) if value is not None else None


@router.get("/schedule/exceptions")
async def list_exceptions(
    trainer: CurrentTrainer,
    session: SessionDep,
    start: Annotated[date, Query(alias="from")],
    end: Annotated[date, Query(alias="to")],
) -> list[ExceptionOut]:
    exceptions = await schedule.list_exceptions(session, trainer, start, end)
    return [ExceptionOut.of(exc) for exc in exceptions]


@router.post("/schedule/exceptions", status_code=status.HTTP_201_CREATED)
async def create_exception(
    body: ExceptionIn, trainer: CurrentTrainer, session: SessionDep
) -> ExceptionOut:
    data = schedule.ExceptionData(body.day, body.kind, body.start, body.end)
    try:
        exc = await schedule.create_exception(session, trainer, data)
    except schedule.ScheduleError as error:
        raise _bad_request(error) from None
    return ExceptionOut.of(exc)


@router.delete("/schedule/exceptions/{exception_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exception(exception_id: int, trainer: CurrentTrainer, session: SessionDep) -> None:
    try:
        await schedule.delete_exception(session, trainer, exception_id)
    except schedule.NotFound:
        raise NOT_FOUND from None


# --- Окошки ---


class SlotOut(BaseModel):
    service_id: int
    starts_at: datetime
    ends_at: datetime


@router.get("/slots")
async def list_slots(
    trainer: CurrentTrainer,
    session: SessionDep,
    start: Annotated[date | None, Query(alias="from")] = None,
    days: Annotated[int, Query(ge=1, le=MAX_SLOT_DAYS)] = 14,
    service_id: int | None = None,
) -> list[SlotOut]:
    """Свободные окошки на days дней. По умолчанию с сегодняшнего дня тренера."""
    now = datetime.now(UTC)
    if start is None:
        start = now.astimezone(ZoneInfo(trainer.timezone)).date()
    slots = await schedule.trainer_slots(session, trainer, start, days, now, service_id)
    return [
        SlotOut(service_id=slot.service_id, starts_at=slot.starts_at, ends_at=slot.ends_at)
        for slot in slots
    ]
