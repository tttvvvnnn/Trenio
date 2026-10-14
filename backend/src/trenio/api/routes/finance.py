"""Финансы тренера: сводка за месяц и год, подробности месяца и прогноз денег."""

from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from trenio.api.deps import CurrentTrainer, SessionDep
from trenio.api.routes.bookings import PersonOut
from trenio.services import finance, packages

router = APIRouter(prefix="/trainer/finance", tags=["finance"])

MonthQuery = Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]


class MonthPointOut(BaseModel):
    month: str
    received: int
    worked: int


class MonthSummaryOut(BaseModel):
    month: str
    # Получено: оплаты блоков по датам и разовые занятия
    received: int
    received_prev: int
    incomes_count: int
    # Отработано: стоимость проведённых и списанных занятий
    worked: int
    worked_sessions: int
    clients: int
    # Сейчас, без привязки к месяцу: долги по блокам и аванс клиентов
    debt: int
    debt_clients: int
    advance: int
    # Оставшиеся в месяце записи и их стоимость
    planned: int
    planned_count: int
    from_packages: int
    from_one_off: int
    # Последние полгода, заканчивая этим месяцем
    chart: list[MonthPointOut]


def _month(trainer: CurrentTrainer, month: str | None) -> str:
    if month is not None:
        return month
    return finance.month_key(packages.trainer_today(trainer, datetime.now(UTC)))


def _points(points: list[finance.MonthPoint]) -> list[MonthPointOut]:
    return [MonthPointOut(month=p.month, received=p.received, worked=p.worked) for p in points]


@router.get("/summary")
async def get_summary(
    trainer: CurrentTrainer, session: SessionDep, month: MonthQuery = None
) -> MonthSummaryOut:
    books = await finance.load(session, trainer, datetime.now(UTC))
    summary = finance.month_summary(books, _month(trainer, month))
    return MonthSummaryOut(
        month=summary.month,
        received=summary.received,
        received_prev=summary.received_prev,
        incomes_count=summary.incomes_count,
        worked=summary.worked,
        worked_sessions=summary.worked_sessions,
        clients=summary.clients,
        debt=summary.debt,
        debt_clients=summary.debt_clients,
        advance=summary.advance,
        planned=summary.planned,
        planned_count=summary.planned_count,
        from_packages=summary.from_packages,
        from_one_off=summary.from_one_off,
        chart=_points(summary.chart),
    )


class YearOut(BaseModel):
    year: int
    received: int
    worked: int
    worked_sessions: int
    months: list[MonthPointOut]


@router.get("/year")
async def get_year(
    trainer: CurrentTrainer,
    session: SessionDep,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
) -> YearOut:
    books = await finance.load(session, trainer, datetime.now(UTC))
    year = year or books.today.year
    months = finance.year_chart(books, year)
    return YearOut(
        year=year,
        received=sum(m.received for m in months),
        worked=sum(m.worked for m in months),
        worked_sessions=sum(books.ledger.sessions(m.month) for m in months),
        months=_points(months),
    )


class IncomeOut(BaseModel):
    day: date
    client: PersonOut
    # payment — оплата блока, one_off — разовое занятие
    kind: str
    label: str
    amount: int


class ClientMonthOut(BaseModel):
    client: PersonOut
    received: int
    worked: int
    sessions: int


class MonthDetailsOut(BaseModel):
    month: str
    incomes: list[IncomeOut]
    clients: list[ClientMonthOut]


@router.get("/month")
async def get_month(
    trainer: CurrentTrainer, session: SessionDep, month: MonthQuery = None
) -> MonthDetailsOut:
    key = _month(trainer, month)
    books = await finance.load(session, trainer, datetime.now(UTC))
    incomes = finance.month_incomes(books, key)
    clients = finance.month_clients(books, key)
    users = await finance.clients_by_id(
        session, [i.client_id for i in incomes] + [c.client_id for c in clients]
    )
    return MonthDetailsOut(
        month=key,
        incomes=[
            IncomeOut(
                day=i.day,
                client=PersonOut.of(users[i.client_id]),
                kind=i.kind,
                label=i.label,
                amount=i.amount,
            )
            for i in incomes
        ],
        clients=[
            ClientMonthOut(
                client=PersonOut.of(users[c.client_id]),
                received=c.received,
                worked=c.worked,
                sessions=c.sessions,
            )
            for c in clients
        ],
    )


class DueOut(BaseModel):
    client: PersonOut
    package_id: int
    package_name: str
    price: int
    paid: int
    due: int


class RenewalOut(BaseModel):
    client: PersonOut
    package_id: int
    package_name: str
    sessions_count: int
    left: int
    # Оценка продления: цена текущего блока
    price: int


class ForecastOut(BaseModel):
    days: int
    total: int
    one_off: int
    one_off_count: int
    dues: list[DueOut]
    renewals: list[RenewalOut]


@router.get("/forecast")
async def get_forecast(trainer: CurrentTrainer, session: SessionDep) -> ForecastOut:
    books = await finance.load(session, trainer, datetime.now(UTC))
    result = finance.money_forecast(books)
    users = await finance.clients_by_id(
        session,
        [d.package.client_id for d in result.dues] + [r.package.client_id for r in result.renewals],
    )
    return ForecastOut(
        days=result.days,
        total=result.total,
        one_off=result.one_off,
        one_off_count=result.one_off_count,
        dues=[
            DueOut(
                client=PersonOut.of(users[d.package.client_id]),
                package_id=d.package.id,
                package_name=d.package.name,
                price=d.package.price,
                paid=packages.paid(d.package),
                due=d.amount,
            )
            for d in result.dues
        ],
        renewals=[
            RenewalOut(
                client=PersonOut.of(users[r.package.client_id]),
                package_id=r.package.id,
                package_name=r.package.name,
                sessions_count=r.package.sessions_count,
                left=r.left,
                price=r.package.price,
            )
            for r in result.renewals
        ],
    )
