"""Расчёт свободных окошек тренера.

Окошки не хранятся в базе: их считаем на лету из недельного шаблона и исключений.
Так правка шаблона сразу меняет расписание. Вычитание уже занятых записей добавится
на этапе 5 вместе с бронированием.

Здесь только чистые функции без базы, чтобы расчёт легко покрыть тестами.
"""

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

# Интервал внутри дня в минутах от полуночи: [start, end)
Interval = tuple[int, int]


class ExceptionKind(StrEnum):
    # Тренер не работает: весь день или часть дня
    CLOSED = "closed"
    # Разовое дополнительное окно сверх шаблона
    EXTRA = "extra"


@dataclass(frozen=True, slots=True)
class ServiceSpec:
    id: int
    duration_min: int


@dataclass(frozen=True, slots=True)
class RuleSpec:
    weekday: int  # 0 — понедельник, как date.weekday()
    start: time
    end: time
    # Пустой набор — в это время доступны все активные услуги
    service_ids: frozenset[int]


@dataclass(frozen=True, slots=True)
class ExceptionSpec:
    day: date
    kind: ExceptionKind
    # Без времени закрытие действует на весь день; у доп. окна время обязательно
    start: time | None
    end: time | None


@dataclass(frozen=True, slots=True)
class Slot:
    service_id: int
    starts_at: datetime  # в UTC
    ends_at: datetime


def _minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def subtract(windows: Iterable[Interval], holes: Sequence[Interval]) -> list[Interval]:
    """Вычитает из окон закрытые промежутки."""
    result = list(windows)
    for hole_start, hole_end in holes:
        next_result: list[Interval] = []
        for start, end in result:
            if hole_end <= start or hole_start >= end:
                next_result.append((start, end))
                continue
            if start < hole_start:
                next_result.append((start, hole_start))
            if hole_end < end:
                next_result.append((hole_end, end))
        result = next_result
    return result


def _local_to_utc(day: date, minute: int, tz: ZoneInfo) -> datetime:
    local = datetime.combine(day, time()) + timedelta(minutes=minute)
    return local.replace(tzinfo=tz).astimezone(UTC)


def day_windows(
    day: date,
    services: Sequence[ServiceSpec],
    rules: Iterable[RuleSpec],
    exceptions: Iterable[ExceptionSpec],
) -> dict[int, list[Interval]]:
    """Рабочие окна дня по каждой услуге: шаблон плюс доп. окна минус закрытия."""
    all_ids = frozenset(service.id for service in services)
    windows: dict[int, list[Interval]] = {service_id: [] for service_id in all_ids}
    for rule in rules:
        if rule.weekday != day.weekday():
            continue
        for service_id in rule.service_ids or all_ids:
            if service_id in windows:
                windows[service_id].append((_minutes(rule.start), _minutes(rule.end)))

    closed: list[Interval] = []
    for exc in exceptions:
        if exc.day != day:
            continue
        if exc.kind is ExceptionKind.EXTRA and exc.start is not None and exc.end is not None:
            for service_id in all_ids:
                windows[service_id].append((_minutes(exc.start), _minutes(exc.end)))
        elif exc.kind is ExceptionKind.CLOSED:
            if exc.start is None or exc.end is None:
                closed.append((0, 24 * 60))
            else:
                closed.append((_minutes(exc.start), _minutes(exc.end)))
    return {service_id: subtract(found, closed) for service_id, found in windows.items()}


def free_slots(
    *,
    start_day: date,
    days: int,
    timezone: str,
    services: Sequence[ServiceSpec],
    rules: Collection[RuleSpec],
    exceptions: Collection[ExceptionSpec],
    now: datetime,
) -> list[Slot]:
    """Окошки на days дней начиная с start_day (даты по часовому поясу тренера).

    Окно нарезается шагом, равным длительности услуги, от начала окна:
    10:00–14:00 при 60 минутах даёт 10, 11, 12, 13. Хвост короче услуги отбрасывается.
    Прошедшие окошки не показываем.
    """
    tz = ZoneInfo(timezone)
    durations = {service.id: service.duration_min for service in services}
    found: set[Slot] = set()
    for offset in range(days):
        day = start_day + timedelta(days=offset)
        for service_id, windows in day_windows(day, services, rules, exceptions).items():
            duration = durations[service_id]
            for window_start, window_end in windows:
                minute = window_start
                while minute + duration <= window_end:
                    starts_at = _local_to_utc(day, minute, tz)
                    if starts_at >= now:
                        ends_at = _local_to_utc(day, minute + duration, tz)
                        found.add(Slot(service_id, starts_at, ends_at))
                    minute += duration
    # Перекрывающиеся правила дают одинаковые окошки: set убирает дубли
    return sorted(found, key=lambda slot: (slot.starts_at, slot.service_id))
