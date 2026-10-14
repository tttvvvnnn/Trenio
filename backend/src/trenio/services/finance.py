"""Финансы тренера: сколько денег получено, сколько отработано и чего ждать.

Две разные «выручки»:
- получено — деньги по датам: оплаты блоков и разовые занятия;
- отработано — стоимость проведённых занятий: цена блока делится на число занятий в нём,
  пропуск со списанием тоже считается.
Разовое занятие считаем оплаченным по цене услуги в день, когда тренер отметил его
«прошла» или «пропуск, списать»: отдельного учёта оплат разовых нет.
Разница между полученным и отработанным по действующим блокам — аванс клиентов.

Всё считается в памяти по блокам и записям тренера: их сотни, а не миллионы.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.db.models import Booking, Package, PackageSession, Trainer, User
from trenio.services import packages
from trenio.services.packages import CHARGED, Forecast, PackageStatus

# На сколько дней вперёд прогноз денег
FORECAST_DAYS = 30
# Сколько месяцев на графике
CHART_MONTHS = 6


def month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def month_start(key: str) -> date:
    year, month = key.split("-")
    return date(int(year), int(month), 1)


def shift_month(key: str, months: int) -> str:
    start = month_start(key)
    index = start.year * 12 + start.month - 1 + months
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


@dataclass(frozen=True)
class Income:
    """Пришедшие деньги: оплата блока или разовое занятие."""

    day: date
    client_id: int
    kind: Literal["payment", "one_off"]
    # Название блока или услуги разового занятия
    label: str
    amount: int


@dataclass(frozen=True)
class Work:
    """Проведённое (списанное) занятие и его стоимость."""

    day: date
    client_id: int
    value: float


@dataclass
class Ledger:
    incomes: list[Income] = field(default_factory=list)
    work: list[Work] = field(default_factory=list)

    def received(self, key: str) -> int:
        return sum(i.amount for i in self.incomes if month_key(i.day) == key)

    def worked(self, key: str) -> int:
        return round(sum(w.value for w in self.work if month_key(w.day) == key))

    def sessions(self, key: str) -> int:
        return sum(1 for w in self.work if month_key(w.day) == key)


def unit_price(package: Package) -> float:
    return package.price / package.sessions_count


def build_ledger(trainer_packages: Iterable[Package], one_offs: Iterable[Booking]) -> Ledger:
    ledger = Ledger()
    for package in trainer_packages:
        for payment in package.payments:
            ledger.incomes.append(
                Income(payment.paid_on, package.client_id, "payment", package.name, payment.amount)
            )
        for package_session in package.sessions:
            ledger.work.append(Work(package_session.day, package.client_id, unit_price(package)))
    for booking in one_offs:
        day = packages.booking_day(booking)
        price = booking.service.price or 0
        name = booking.service.name
        ledger.incomes.append(Income(day, booking.client_id, "one_off", name, price))
        ledger.work.append(Work(day, booking.client_id, price))
    return ledger


async def charged_one_offs(session: AsyncSession, trainer: Trainer) -> Sequence[Booking]:
    """Отмеченные со списанием записи, которые не легли ни в один блок."""
    stmt = (
        select(Booking)
        .outerjoin(PackageSession, PackageSession.booking_id == Booking.id)
        .where(
            Booking.trainer_id == trainer.id,
            Booking.attendance.in_(CHARGED),
            PackageSession.id.is_(None),
        )
        .order_by(Booking.starts_at, Booking.id)
    )
    return (await session.scalars(stmt)).all()


@dataclass(frozen=True)
class Books:
    """Всё, из чего считаются финансы тренера."""

    trainer: Trainer
    packages: Sequence[Package]
    ledger: Ledger
    forecast: Forecast
    today: date
    now: datetime


async def load(session: AsyncSession, trainer: Trainer, now: datetime) -> Books:
    trainer_packages = await packages.list_trainer_packages(session, trainer)
    one_offs = await charged_one_offs(session, trainer)
    return Books(
        trainer=trainer,
        packages=trainer_packages,
        ledger=build_ledger(trainer_packages, one_offs),
        forecast=await packages.forecast(session, [trainer.id]),
        today=packages.trainer_today(trainer, now),
        now=now,
    )


def planned_value(books: Books, booking: Booking) -> int:
    """Сколько стоит будущее занятие: доля блока или цена услуги для разового."""
    charge = books.forecast.plan.get(booking.id)
    if charge is not None:
        return round(unit_price(charge.package))
    return booking.service.price or 0


def upcoming(books: Books, until: date) -> list[Booking]:
    """Будущие активные записи до конца дня until."""
    return [
        b
        for b in books.forecast.bookings
        if b.starts_at > books.now and packages.booking_day(b) <= until
    ]


# --- Сводка за месяц ---


@dataclass(frozen=True)
class MonthPoint:
    month: str
    received: int
    worked: int


@dataclass(frozen=True)
class MonthSummary:
    month: str
    received: int
    received_prev: int
    incomes_count: int
    worked: int
    worked_sessions: int
    # Сколько клиентов занимались в месяце
    clients: int
    # Сейчас: сколько клиенты должны доплатить по блокам и сколько их
    debt: int
    debt_clients: int
    # Сейчас: деньги за действующие блоки, которые ещё не отработаны
    advance: int
    # Оставшиеся в месяце записи и их стоимость; для прошлых месяцев нули
    planned: int
    planned_count: int
    from_packages: int
    from_one_off: int
    chart: list[MonthPoint]


def debt(books: Books) -> tuple[int, int]:
    owing = [p for p in books.packages if p.closed_at is None and packages.due(p) > 0]
    return sum(packages.due(p) for p in owing), len({p.client_id for p in owing})


def advance(books: Books) -> int:
    total = 0.0
    for package in books.packages:
        if packages.status(package, books.today) is PackageStatus.ACTIVE:
            worked = packages.used(package) * unit_price(package)
            total += max(packages.paid(package) - worked, 0)
    return round(total)


def chart(books: Books, last: str, months: int) -> list[MonthPoint]:
    keys = [shift_month(last, offset) for offset in range(1 - months, 1)]
    return [MonthPoint(k, books.ledger.received(k), books.ledger.worked(k)) for k in keys]


def month_summary(books: Books, key: str) -> MonthSummary:
    ledger = books.ledger
    incomes = [i for i in ledger.incomes if month_key(i.day) == key]
    owed, owing_clients = debt(books)
    end = month_start(shift_month(key, 1)) - timedelta(days=1)
    rest = upcoming(books, end) if end >= books.today else []
    return MonthSummary(
        month=key,
        received=sum(i.amount for i in incomes),
        received_prev=ledger.received(shift_month(key, -1)),
        incomes_count=len(incomes),
        worked=ledger.worked(key),
        worked_sessions=ledger.sessions(key),
        clients=len({w.client_id for w in ledger.work if month_key(w.day) == key}),
        debt=owed,
        debt_clients=owing_clients,
        advance=advance(books),
        planned=sum(planned_value(books, b) for b in rest),
        planned_count=len(rest),
        from_packages=sum(i.amount for i in incomes if i.kind == "payment"),
        from_one_off=sum(i.amount for i in incomes if i.kind == "one_off"),
        chart=chart(books, key, CHART_MONTHS),
    )


def year_chart(books: Books, year: int) -> list[MonthPoint]:
    return chart(books, f"{year:04d}-12", 12)


# --- Подробности месяца ---


@dataclass(frozen=True)
class ClientMonth:
    client_id: int
    received: int
    worked: int
    sessions: int


def month_incomes(books: Books, key: str) -> list[Income]:
    """Деньги месяца, свежие первыми."""
    found = [i for i in books.ledger.incomes if month_key(i.day) == key]
    return sorted(found, key=lambda i: i.day, reverse=True)


def month_clients(books: Books, key: str) -> list[ClientMonth]:
    received: dict[int, int] = {}
    worked: dict[int, float] = {}
    sessions: dict[int, int] = {}
    for income in books.ledger.incomes:
        if month_key(income.day) == key:
            received[income.client_id] = received.get(income.client_id, 0) + income.amount
    for work in books.ledger.work:
        if month_key(work.day) == key:
            worked[work.client_id] = worked.get(work.client_id, 0) + work.value
            sessions[work.client_id] = sessions.get(work.client_id, 0) + 1
    result = [
        ClientMonth(c, received.get(c, 0), round(worked.get(c, 0)), sessions.get(c, 0))
        for c in set(received) | set(worked)
    ]
    return sorted(result, key=lambda c: (-c.received, -c.worked, c.client_id))


# --- Прогноз ---


@dataclass(frozen=True)
class Due:
    package: Package
    amount: int


@dataclass(frozen=True)
class Renewal:
    package: Package
    left: int


@dataclass(frozen=True)
class MoneyForecast:
    days: int
    total: int
    # Будущие разовые занятия: оплатят по цене услуги
    one_off: int
    one_off_count: int
    dues: list[Due]
    # Блоки, где осталось 1–2 занятия: оценка продления по цене текущего блока
    renewals: list[Renewal]


def money_forecast(books: Books) -> MoneyForecast:
    until = books.today + timedelta(days=FORECAST_DAYS)
    one_offs = [b for b in upcoming(books, until) if books.forecast.plan.get(b.id) is None]
    one_off = sum(b.service.price or 0 for b in one_offs)
    dues = [
        Due(p, packages.due(p))
        for p in books.packages
        if p.closed_at is None and packages.due(p) > 0
    ]
    dues.sort(key=lambda d: -d.amount)
    # Клиент с другим действующим блоком, где занятий ещё много, продлевать пока не будет
    stocked = {
        p.client_id
        for p in books.packages
        if packages.status(p, books.today) is PackageStatus.ACTIVE
        and packages.left(p) > packages.ENDING_SOON_LEFT
    }
    renewals = [
        Renewal(p, packages.left(p))
        for p in books.packages
        if packages.ending_soon(p, books.today) and p.client_id not in stocked
    ]
    renewals.sort(key=lambda r: (r.left, r.package.id))
    total = one_off + sum(d.amount for d in dues) + sum(r.package.price for r in renewals)
    return MoneyForecast(FORECAST_DAYS, total, one_off, len(one_offs), dues, renewals)


async def clients_by_id(session: AsyncSession, ids: Iterable[int]) -> dict[int, User]:
    ids = set(ids)
    if not ids:
        return {}
    users = (await session.scalars(select(User).where(User.id.in_(ids)))).all()
    return {user.id: user for user in users}
