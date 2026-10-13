"""Расчёт окошек без базы: шаблон, часы на даты, часовые пояса."""

from datetime import UTC, date, datetime, time, timedelta

from trenio.services.slots import (
    BusySpec,
    DaySpec,
    RuleSpec,
    ServiceSpec,
    Slot,
    WindowSpec,
    free_slots,
    subtract,
)

MONDAY = date(2026, 10, 12)
PERSONAL = ServiceSpec(id=1, duration_min=60)
LONG = ServiceSpec(id=2, duration_min=90)
LONG_AGO = datetime(2000, 1, 1, tzinfo=UTC)


def monday_rule(start: int, end: int, service_ids: frozenset[int] = frozenset()) -> RuleSpec:
    return RuleSpec(weekday=0, start=time(start), end=time(end), service_ids=service_ids)


def slots(
    *,
    services: list[ServiceSpec],
    rules: list[RuleSpec],
    custom_days: list[DaySpec] | None = None,
    busy: list[BusySpec] | None = None,
    start_day: date = MONDAY,
    days: int = 1,
    timezone: str = "Europe/Moscow",
    now: datetime = LONG_AGO,
) -> list[Slot]:
    return free_slots(
        start_day=start_day,
        days=days,
        timezone=timezone,
        services=services,
        rules=rules,
        custom_days=custom_days or [],
        now=now,
        busy=busy or [],
    )


def utc(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=UTC)


def starts(found: list[Slot], service_id: int = 1) -> list[datetime]:
    return [slot.starts_at for slot in found if slot.service_id == service_id]


def test_window_is_cut_by_service_duration() -> None:
    found = slots(services=[PERSONAL], rules=[monday_rule(10, 14)])
    # Москва = UTC+3: 10:00 МСК это 07:00 UTC
    assert starts(found) == [utc(MONDAY, h) for h in (7, 8, 9, 10)]
    assert found[0].ends_at == utc(MONDAY, 8)


def test_tail_shorter_than_service_is_dropped() -> None:
    found = slots(services=[LONG], rules=[monday_rule(10, 14)])
    # 10:00 и 11:30; 13:00 + 90 минут вылезает за 14:00
    assert starts(found, 2) == [utc(MONDAY, 7), utc(MONDAY, 8, 30)]


def test_rule_limited_to_some_services() -> None:
    found = slots(services=[PERSONAL, LONG], rules=[monday_rule(10, 12, frozenset({2}))])
    assert starts(found, 1) == []
    assert starts(found, 2) == [utc(MONDAY, 7)]


def test_empty_service_list_means_all_services() -> None:
    found = slots(services=[PERSONAL, LONG], rules=[monday_rule(10, 12)])
    assert starts(found, 1) == [utc(MONDAY, 7), utc(MONDAY, 8)]
    assert starts(found, 2) == [utc(MONDAY, 7)]


def test_rules_apply_only_on_their_weekday() -> None:
    found = slots(services=[PERSONAL], rules=[monday_rule(10, 11)], days=14)
    assert starts(found) == [utc(MONDAY, 7), utc(date(2026, 10, 19), 7)]


def test_custom_day_replaces_template() -> None:
    day_off = DaySpec(MONDAY, ())
    assert slots(services=[PERSONAL], rules=[monday_rule(10, 14)], custom_days=[day_off]) == []

    # Свои часы на дату: шаблон 10–14 не действует, только 16–18
    evening = DaySpec(MONDAY, (WindowSpec(time(16), time(18)),))
    found = slots(services=[PERSONAL], rules=[monday_rule(10, 14)], custom_days=[evening])
    assert starts(found) == [utc(MONDAY, 13), utc(MONDAY, 14)]


def test_custom_day_on_other_date_is_ignored() -> None:
    other = DaySpec(date(2026, 10, 13), ())
    found = slots(services=[PERSONAL], rules=[monday_rule(10, 11)], custom_days=[other])
    assert len(found) == 1


def test_custom_day_windows_respect_services() -> None:
    sunday = date(2026, 10, 18)
    custom = DaySpec(
        sunday,
        (
            WindowSpec(time(9), time(10, 30)),
            WindowSpec(time(12), time(13), frozenset({1})),
        ),
    )
    found = slots(services=[PERSONAL, LONG], rules=[], custom_days=[custom], start_day=sunday)
    assert starts(found, 1) == [utc(sunday, 6), utc(sunday, 9)]
    assert starts(found, 2) == [utc(sunday, 6)]


def test_overlapping_rules_do_not_duplicate_slots() -> None:
    found = slots(services=[PERSONAL], rules=[monday_rule(10, 12), monday_rule(10, 12)])
    assert len(found) == 2


def test_past_slots_are_hidden() -> None:
    now = utc(MONDAY, 8, 15)  # 11:15 МСК
    found = slots(services=[PERSONAL], rules=[monday_rule(10, 14)], now=now)
    assert starts(found) == [utc(MONDAY, 9), utc(MONDAY, 10)]


def test_local_time_follows_daylight_saving() -> None:
    # В Берлине 25.10.2026 переход на зимнее время: UTC+2 до него, UTC+1 после
    saturday, monday = date(2026, 10, 24), date(2026, 10, 26)
    rules = [
        RuleSpec(weekday=5, start=time(10), end=time(11), service_ids=frozenset()),
        RuleSpec(weekday=0, start=time(10), end=time(11), service_ids=frozenset()),
    ]
    found = slots(
        services=[PERSONAL], rules=rules, start_day=saturday, days=3, timezone="Europe/Berlin"
    )
    assert starts(found) == [utc(saturday, 8), utc(monday, 9)]


def test_subtract_intervals() -> None:
    assert subtract([(0, 100)], [(20, 30), (50, 60)]) == [(0, 20), (30, 50), (60, 100)]
    assert subtract([(0, 100)], [(0, 100)]) == []
    assert subtract([(10, 20)], [(30, 40)]) == [(10, 20)]


GROUP = ServiceSpec(id=3, duration_min=60, capacity=2)


def booked(service: ServiceSpec, hour: int, minute: int = 0) -> BusySpec:
    starts_at = utc(MONDAY, hour, minute)
    return BusySpec(service.id, starts_at, starts_at + timedelta(minutes=service.duration_min))


def test_booking_takes_slot_for_every_service() -> None:
    # 10:00 МСК занято персональной: ни персональной, ни длинной в это время уже нет
    found = slots(
        services=[PERSONAL, LONG], rules=[monday_rule(10, 14)], busy=[booked(PERSONAL, 7)]
    )
    assert starts(found, 1) == [utc(MONDAY, h) for h in (8, 9, 10)]
    # Длинная 11:30 не пересекается с 10:00–11:00, а 10:00 пересекается
    assert starts(found, 2) == [utc(MONDAY, 8, 30)]


def test_group_slot_stays_while_seats_left() -> None:
    rules = [monday_rule(10, 12)]
    found = slots(services=[GROUP], rules=rules, busy=[booked(GROUP, 7)])
    assert [(slot.starts_at, slot.seats_left) for slot in found] == [
        (utc(MONDAY, 7), 1),
        (utc(MONDAY, 8), 2),
    ]
    full = slots(services=[GROUP], rules=rules, busy=[booked(GROUP, 7), booked(GROUP, 7)])
    assert starts(full, 3) == [utc(MONDAY, 8)]


def test_group_slot_is_closed_by_other_service() -> None:
    # Персональная в 10:00 занимает тренера: в группу на это время уже не записаться
    found = slots(
        services=[PERSONAL, GROUP], rules=[monday_rule(10, 11)], busy=[booked(PERSONAL, 7)]
    )
    assert found == []


def test_start_step_shorter_than_service() -> None:
    found = free_slots(
        start_day=MONDAY,
        days=1,
        timezone="Europe/Moscow",
        services=[PERSONAL],
        rules=[monday_rule(10, 12)],
        now=LONG_AGO,
        step_min=20,
    )
    # 10:00, 10:20, 10:40, 11:00; 11:20 + час уже не помещается до 12:00
    assert starts(found) == [utc(MONDAY, 7), utc(MONDAY, 7, 20), utc(MONDAY, 7, 40), utc(MONDAY, 8)]
