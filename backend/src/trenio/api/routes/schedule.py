"""Услуги, недельный шаблон, часы на даты и окошки тренера."""

from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from trenio.api.deps import CurrentTrainer, SessionDep
from trenio.db.models import ScheduleRule
from trenio.services import schedule
from trenio.services.slots import Slot

router = APIRouter(prefix="/trainer", tags=["schedule"])

# Окошки отдаём не больше чем на шесть недель с запасом: столько занимает месяц в календаре
MAX_SLOT_DAYS = 62

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


# --- Часы на даты ---

# Календарь расписания отдаём не больше чем на шесть недель с запасом
MAX_CALENDAR_DAYS = 62


class WindowIO(BaseModel):
    start: time
    end: time
    service_ids: list[int] = Field(
        default_factory=list, description="Пустой список — все активные услуги"
    )

    _trim_times = field_validator("start", "end")(_trim)

    @classmethod
    def of(cls, window: schedule.WindowData) -> "WindowIO":
        return cls(start=window.start, end=window.end, service_ids=list(window.service_ids))

    def to_data(self) -> schedule.WindowData:
        return schedule.WindowData(self.start, self.end, tuple(self.service_ids))


class DayHoursOut(BaseModel):
    day: date
    # true — на дату заданы свои часы, false — работает недельный шаблон
    custom: bool
    # Пустой список — выходной
    windows: list[WindowIO]


@router.get("/schedule/days")
async def list_days(
    trainer: CurrentTrainer,
    session: SessionDep,
    start: Annotated[date, Query(alias="from")],
    days: Annotated[int, Query(ge=1, le=MAX_CALENDAR_DAYS)] = 42,
) -> list[DayHoursOut]:
    """Часы по датам: свои или из недельного шаблона."""
    found = await schedule.day_hours(session, trainer, start, days)
    return [
        DayHoursOut(
            day=item.day, custom=item.custom, windows=[WindowIO.of(w) for w in item.windows]
        )
        for item in found
    ]


class DaysIn(BaseModel):
    days: list[date] = Field(min_length=1, max_length=schedule.MAX_DAYS_AT_ONCE)
    # Пустой список — выходной
    windows: list[WindowIO] = Field(default_factory=list, max_length=schedule.MAX_WINDOWS)


@router.put("/schedule/days", status_code=status.HTTP_204_NO_CONTENT)
async def set_days(body: DaysIn, trainer: CurrentTrainer, session: SessionDep) -> None:
    """Одинаковые часы на несколько дат. Полностью заменяют шаблон в эти дни."""
    try:
        await schedule.set_days(
            session, trainer, body.days, [window.to_data() for window in body.windows]
        )
    except schedule.ScheduleError as error:
        raise _bad_request(error) from None
    except schedule.NotFound:
        raise HTTPException(422, "Услуга не найдена") from None


class DaysResetIn(BaseModel):
    days: list[date] = Field(min_length=1, max_length=schedule.MAX_DAYS_AT_ONCE)


@router.post("/schedule/days/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_days(body: DaysResetIn, trainer: CurrentTrainer, session: SessionDep) -> None:
    """Вернуть даты к недельному шаблону."""
    await schedule.reset_days(session, trainer, body.days)


class CopyWeekIn(BaseModel):
    # Любой день недели, которую повторяем; неделя считается с понедельника
    day: date
    weeks: int = Field(ge=1, le=12)


@router.post("/schedule/days/copy-week", status_code=status.HTTP_204_NO_CONTENT)
async def copy_week(body: CopyWeekIn, trainer: CurrentTrainer, session: SessionDep) -> None:
    """Повторить часы недели на следующие недели."""
    monday = body.day - timedelta(days=body.day.weekday())
    try:
        await schedule.copy_week(session, trainer, monday, body.weeks)
    except schedule.ScheduleError as error:
        raise _bad_request(error) from None


# --- Окошки ---


class SlotOut(BaseModel):
    service_id: int
    starts_at: datetime
    ends_at: datetime
    # Сколько ещё человек можно записать; у индивидуальной услуги всегда 1
    seats_left: int

    @classmethod
    def of(cls, slot: Slot) -> "SlotOut":
        return cls(
            service_id=slot.service_id,
            starts_at=slot.starts_at,
            ends_at=slot.ends_at,
            seats_left=slot.seats_left,
        )


@router.get("/slots")
async def list_slots(
    trainer: CurrentTrainer,
    session: SessionDep,
    start: Annotated[date | None, Query(alias="from")] = None,
    days: Annotated[int, Query(ge=1, le=MAX_SLOT_DAYS)] = 14,
    service_id: int | None = None,
    reschedule: int | None = None,
) -> list[SlotOut]:
    """Свободные окошки на days дней с учётом записей. По умолчанию с сегодняшнего дня тренера.

    reschedule — запись, которую переносят: её нынешнее время тоже считается свободным.
    Чужой id ничего не освободит: исключаются только записи этого тренера.
    """
    now = datetime.now(UTC)
    if start is None:
        start = now.astimezone(ZoneInfo(trainer.timezone)).date()
    slots = await schedule.trainer_slots(session, trainer, start, days, now, service_id, reschedule)
    return [SlotOut.of(slot) for slot in slots]
