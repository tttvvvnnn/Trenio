"""Услуги и расписание тренера: CRUD и окошки.

Все функции получают тренера и работают только с его строками, поэтому чужую услугу
или правило не достать даже по известному id.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.db.models import (
    ACTIVE_BOOKING_STATUSES,
    Booking,
    ScheduleException,
    ScheduleRule,
    Service,
    Trainer,
)
from trenio.services.slots import (
    BusySpec,
    ExceptionKind,
    ExceptionSpec,
    RuleSpec,
    ServiceSpec,
    Slot,
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


# --- Исключения ---


@dataclass(frozen=True, slots=True)
class ExceptionData:
    day: date
    kind: ExceptionKind
    start: time | None = None
    end: time | None = None


async def list_exceptions(
    session: AsyncSession, trainer: Trainer, start_day: date, end_day: date
) -> Sequence[ScheduleException]:
    stmt = (
        select(ScheduleException)
        .where(
            ScheduleException.trainer_id == trainer.id,
            ScheduleException.day >= start_day,
            ScheduleException.day <= end_day,
        )
        .order_by(ScheduleException.day, ScheduleException.start_time, ScheduleException.id)
    )
    return (await session.scalars(stmt)).all()


async def create_exception(
    session: AsyncSession, trainer: Trainer, data: ExceptionData
) -> ScheduleException:
    if (data.start is None) != (data.end is None):
        raise ScheduleError("Укажите и начало, и конец, или ни то ни другое")
    if data.start is not None and data.end is not None:
        _check_range(data.start, data.end)
    elif data.kind is ExceptionKind.EXTRA:
        raise ScheduleError("У дополнительного окна нужно время")
    exception = ScheduleException(
        trainer_id=trainer.id,
        day=data.day,
        kind=data.kind.value,
        start_time=data.start,
        end_time=data.end,
    )
    session.add(exception)
    await session.commit()
    await session.refresh(exception)
    return exception


async def delete_exception(session: AsyncSession, trainer: Trainer, exception_id: int) -> None:
    exception = await session.scalar(
        select(ScheduleException).where(
            ScheduleException.id == exception_id, ScheduleException.trainer_id == trainer.id
        )
    )
    if exception is None:
        raise NotFound(exception_id)
    await session.delete(exception)
    await session.commit()


# --- Окошки ---


async def active_bookings(
    session: AsyncSession, trainer: Trainer, start: datetime, end: datetime
) -> Sequence[Booking]:
    """Записи, которые занимают время тренера и пересекаются с [start, end)."""
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
    return (await session.scalars(stmt)).all()


async def trainer_slots(
    session: AsyncSession,
    trainer: Trainer,
    start_day: date,
    days: int,
    now: datetime,
    service_id: int | None = None,
) -> list[Slot]:
    services = await list_services(session, trainer)
    if service_id is not None:
        services = [service for service in services if service.id == service_id]
    rules = await list_rules(session, trainer)
    exceptions = await list_exceptions(
        session, trainer, start_day, start_day + timedelta(days=days - 1)
    )
    # С запасом в сутки по краям: границы дней в поясе тренера не совпадают с UTC
    busy = await active_bookings(
        session,
        trainer,
        datetime.combine(start_day - timedelta(days=1), time(), UTC),
        datetime.combine(start_day + timedelta(days=days + 1), time(), UTC),
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
        exceptions=[
            ExceptionSpec(
                day=exc.day,
                kind=ExceptionKind(exc.kind),
                start=exc.start_time,
                end=exc.end_time,
            )
            for exc in exceptions
        ],
        now=now,
        busy=[BusySpec(b.service_id, b.starts_at, b.ends_at) for b in busy],
        step_min=trainer.slot_step_min,
    )
