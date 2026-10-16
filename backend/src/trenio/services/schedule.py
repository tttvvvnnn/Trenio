"""Услуги и расписание тренера: CRUD и окошки.

Все функции получают тренера и работают только с его строками, поэтому чужую услугу
или правило не достать даже по известному id.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from trenio import realtime
from trenio.db.models import (
    ACTIVE_BOOKING_STATUSES,
    Booking,
    ScheduleDay,
    ScheduleRule,
    Service,
    Trainer,
)
from trenio.services.slots import (
    BusySpec,
    DaySpec,
    RuleSpec,
    ServiceSpec,
    Slot,
    WindowSpec,
    free_slots,
)


class NotFound(LookupError):
    pass


class ScheduleError(ValueError):
    """Данные расписания противоречат друг другу (например, начало позже конца)."""


# --- Услуги ---


@dataclass(frozen=True, slots=True)
class ServiceData:
    name: str
    duration_min: int
    capacity: int = 1
    price: int | None = None
    address: str | None = None


@dataclass(frozen=True, slots=True)
class ServiceChanges:
    """None — поле не меняем. Пустая строка в address очищает адрес."""

    name: str | None = None
    duration_min: int | None = None
    capacity: int | None = None
    price: int | None = None
    clear_price: bool = False
    address: str | None = None
    is_active: bool | None = None


async def list_services(
    session: AsyncSession, trainer: Trainer, include_inactive: bool = False
) -> Sequence[Service]:
    stmt = select(Service).where(Service.trainer_id == trainer.id).order_by(Service.id)
    if not include_inactive:
        stmt = stmt.where(Service.is_active.is_(True))
    return (await session.scalars(stmt)).all()


async def get_service(session: AsyncSession, trainer: Trainer, service_id: int) -> Service:
    service = await session.scalar(
        select(Service).where(Service.id == service_id, Service.trainer_id == trainer.id)
    )
    if service is None:
        raise NotFound(service_id)
    return service


async def create_service(session: AsyncSession, trainer: Trainer, data: ServiceData) -> Service:
    service = Service(
        trainer_id=trainer.id,
        name=data.name,
        duration_min=data.duration_min,
        capacity=data.capacity,
        price=data.price,
        address=data.address or None,
    )
    session.add(service)
    await session.commit()
    await session.refresh(service)
    return service


async def update_service(
    session: AsyncSession, trainer: Trainer, service_id: int, changes: ServiceChanges
) -> Service:
    service = await get_service(session, trainer, service_id)
    if changes.name is not None:
        service.name = changes.name
    if changes.duration_min is not None:
        service.duration_min = changes.duration_min
    if changes.capacity is not None:
        service.capacity = changes.capacity
    if changes.clear_price:
        service.price = None
    elif changes.price is not None:
        service.price = changes.price
    if changes.address is not None:
        service.address = changes.address or None
    if changes.is_active is not None:
        service.is_active = changes.is_active
    await session.commit()
    await session.refresh(service)
    return service


# --- Недельный шаблон ---


@dataclass(frozen=True, slots=True)
class RuleData:
    weekday: int
    start: time
    end: time
    # Пустой список — все активные услуги
    service_ids: Sequence[int] = ()


def _check_range(start: time, end: time) -> None:
    if start >= end:
        raise ScheduleError("Начало должно быть раньше конца")


async def _own_services(
    session: AsyncSession, trainer: Trainer, service_ids: Sequence[int]
) -> list[Service]:
    if not service_ids:
        return []
    found = (
        await session.scalars(
            select(Service).where(
                Service.trainer_id == trainer.id, Service.id.in_(set(service_ids))
            )
        )
    ).all()
    if len(found) != len(set(service_ids)):
        raise NotFound(service_ids)
    return list(found)


async def list_rules(session: AsyncSession, trainer: Trainer) -> Sequence[ScheduleRule]:
    stmt = (
        select(ScheduleRule)
        .where(ScheduleRule.trainer_id == trainer.id)
        .order_by(ScheduleRule.weekday, ScheduleRule.start_time, ScheduleRule.id)
    )
    return (await session.scalars(stmt)).all()


async def _get_rule(session: AsyncSession, trainer: Trainer, rule_id: int) -> ScheduleRule:
    rule = await session.scalar(
        select(ScheduleRule).where(
            ScheduleRule.id == rule_id, ScheduleRule.trainer_id == trainer.id
        )
    )
    if rule is None:
        raise NotFound(rule_id)
    return rule


async def create_rule(session: AsyncSession, trainer: Trainer, data: RuleData) -> ScheduleRule:
    _check_range(data.start, data.end)
    rule = ScheduleRule(
        trainer_id=trainer.id,
        weekday=data.weekday,
        start_time=data.start,
        end_time=data.end,
        services=await _own_services(session, trainer, data.service_ids),
    )
    session.add(rule)
    await session.commit()
    return rule


async def replace_rule(
    session: AsyncSession, trainer: Trainer, rule_id: int, data: RuleData
) -> ScheduleRule:
    _check_range(data.start, data.end)
    rule = await _get_rule(session, trainer, rule_id)
    rule.weekday = data.weekday
    rule.start_time = data.start
    rule.end_time = data.end
    rule.services = await _own_services(session, trainer, data.service_ids)
    await session.commit()
    return rule


async def delete_rule(session: AsyncSession, trainer: Trainer, rule_id: int) -> None:
    await session.delete(await _get_rule(session, trainer, rule_id))
    await session.commit()


# --- Часы на даты ---

# Сколько дней можно поменять за раз и сколько окон бывает в дне
MAX_DAYS_AT_ONCE = 93
MAX_WINDOWS = 12


@dataclass(frozen=True, slots=True)
class WindowData:
    start: time
    end: time
    # Пустой список — все активные услуги
    service_ids: Sequence[int] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "start": self.start.strftime("%H:%M"),
            "end": self.end.strftime("%H:%M"),
            "service_ids": sorted(set(self.service_ids)),
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "WindowData":
        return cls(
            time.fromisoformat(data["start"]),
            time.fromisoformat(data["end"]),
            tuple(data.get("service_ids", ())),
        )

    def spec(self) -> WindowSpec:
        return WindowSpec(self.start, self.end, frozenset(self.service_ids))


@dataclass(frozen=True, slots=True)
class DayHours:
    day: date
    # True — на эту дату заданы свои часы, False — работает недельный шаблон
    custom: bool
    windows: list[WindowData]


def _windows_of(item: ScheduleDay) -> list[WindowData]:
    return [WindowData.from_json(window) for window in item.windows]


async def list_custom_days(
    session: AsyncSession, trainer: Trainer, start_day: date, end_day: date
) -> Sequence[ScheduleDay]:
    stmt = (
        select(ScheduleDay)
        .where(
            ScheduleDay.trainer_id == trainer.id,
            ScheduleDay.day >= start_day,
            ScheduleDay.day <= end_day,
        )
        .order_by(ScheduleDay.day)
    )
    return (await session.scalars(stmt)).all()


async def day_hours(
    session: AsyncSession, trainer: Trainer, start_day: date, days: int
) -> list[DayHours]:
    """Часы по датам: свои, если заданы, иначе из недельного шаблона."""
    end_day = start_day + timedelta(days=days - 1)
    custom = {
        item.day: item for item in await list_custom_days(session, trainer, start_day, end_day)
    }
    rules = await list_rules(session, trainer)
    result = []
    for offset in range(days):
        day = start_day + timedelta(days=offset)
        found = custom.get(day)
        if found is not None:
            result.append(DayHours(day, True, _windows_of(found)))
            continue
        windows = [
            WindowData(rule.start_time, rule.end_time, tuple(s.id for s in rule.services))
            for rule in rules
            if rule.weekday == day.weekday()
        ]
        result.append(DayHours(day, False, windows))
    return result


def _check_days(days: Sequence[date]) -> None:
    if not days or len(set(days)) > MAX_DAYS_AT_ONCE:
        raise ScheduleError(f"Выберите от 1 до {MAX_DAYS_AT_ONCE} дней")


async def set_days(
    session: AsyncSession, trainer: Trainer, days: Sequence[date], windows: Sequence[WindowData]
) -> None:
    """Задать одинаковые часы на несколько дат. Пустой список окон — выходной."""
    _check_days(days)
    if len(windows) > MAX_WINDOWS:
        raise ScheduleError(f"В дне не больше {MAX_WINDOWS} промежутков")
    for window in windows:
        _check_range(window.start, window.end)
    await _own_services(session, trainer, [i for w in windows for i in w.service_ids])
    data = [window.to_json() for window in sorted(windows, key=lambda w: (w.start, w.end))]
    existing = {
        item.day: item for item in await list_custom_days(session, trainer, min(days), max(days))
    }
    for day in set(days):
        found = existing.get(day)
        if found is None:
            session.add(ScheduleDay(trainer_id=trainer.id, day=day, windows=data))
        else:
            found.windows = data
    await session.commit()


async def reset_days(session: AsyncSession, trainer: Trainer, days: Sequence[date]) -> None:
    """Вернуть даты к недельному шаблону."""
    _check_days(days)
    await session.execute(
        delete(ScheduleDay).where(
            ScheduleDay.trainer_id == trainer.id, ScheduleDay.day.in_(set(days))
        )
    )
    # Массовое удаление идёт мимо ORM-объектов: об изменении сообщаем сами
    realtime.mark(session, trainer.id)
    await session.commit()


async def copy_week(session: AsyncSession, trainer: Trainer, week_start: date, weeks: int) -> None:
    """Повторить неделю на следующие weeks недель: дни со своими часами копируются,
    дни по шаблону и на новых неделях остаются по шаблону."""
    if not 1 <= weeks <= 12:
        raise ScheduleError("Можно повторить на 1–12 недель")
    source = await day_hours(session, trainer, week_start, 7)
    for item in source:
        targets = [item.day + timedelta(weeks=k) for k in range(1, weeks + 1)]
        if item.custom:
            await set_days(session, trainer, targets, item.windows)
        else:
            await reset_days(session, trainer, targets)


# --- Окошки ---


async def active_bookings(
    session: AsyncSession,
    trainer: Trainer,
    start: datetime,
    end: datetime,
    exclude_id: int | None = None,
) -> Sequence[Booking]:
    """Записи, которые занимают время тренера и пересекаются с [start, end).

    exclude_id — запись, которую переносят: её нынешнее время для неё самой свободно.
    """
    stmt = (
        select(Booking)
        .where(
            Booking.trainer_id == trainer.id,
            Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            Booking.starts_at < end,
            Booking.ends_at > start,
        )
        .order_by(Booking.starts_at, Booking.id)
    )
    if exclude_id is not None:
        stmt = stmt.where(Booking.id != exclude_id)
    return (await session.scalars(stmt)).all()


async def trainer_slots(
    session: AsyncSession,
    trainer: Trainer,
    start_day: date,
    days: int,
    now: datetime,
    service_id: int | None = None,
    exclude_id: int | None = None,
) -> list[Slot]:
    """Свободные окошки. exclude_id — переносимая запись: её время считается свободным."""
    services = await list_services(session, trainer)
    if service_id is not None:
        services = [service for service in services if service.id == service_id]
    rules = await list_rules(session, trainer)
    custom = await list_custom_days(
        session, trainer, start_day, start_day + timedelta(days=days - 1)
    )
    # С запасом в сутки по краям: границы дней в поясе тренера не совпадают с UTC
    busy = await active_bookings(
        session,
        trainer,
        datetime.combine(start_day - timedelta(days=1), time(), UTC),
        datetime.combine(start_day + timedelta(days=days + 1), time(), UTC),
        exclude_id,
    )
    return free_slots(
        start_day=start_day,
        days=days,
        timezone=trainer.timezone,
        services=[
            ServiceSpec(service.id, service.duration_min, service.capacity) for service in services
        ],
        rules=[
            RuleSpec(
                weekday=rule.weekday,
                start=rule.start_time,
                end=rule.end_time,
                service_ids=frozenset(service.id for service in rule.services),
            )
            for rule in rules
        ],
        custom_days=[
            DaySpec(item.day, tuple(window.spec() for window in _windows_of(item)))
            for item in custom
        ],
        now=now,
        busy=[BusySpec(b.service_id, b.starts_at, b.ends_at) for b in busy],
        step_min=trainer.slot_step_min,
    )
