"""Статистика тренера за месяц."""

from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel

from trenio.api.deps import CurrentTrainer, SessionDep
from trenio.api.routes.bookings import PersonOut
from trenio.api.routes.finance import MonthQuery, month_or_current
from trenio.services import stats

router = APIRouter(prefix="/trainer/stats", tags=["stats"])


class VisitsOut(BaseModel):
    attended: int
    missed_charged: int
    missed_free: int
    # Прошли, но не отмечены
    unmarked: int
    # Ещё впереди в этом месяце
    upcoming: int
    cancelled_by_client: int
    cancelled_by_trainer: int


class WeekdayLoadOut(BaseModel):
    # 0 — понедельник
    weekday: int
    open_minutes: int
    booked_minutes: int


class ClientVisitsOut(BaseModel):
    client: PersonOut
    sessions: int


class LapsedOut(BaseModel):
    client: PersonOut
    last_at: datetime


class StatsOut(BaseModel):
    month: str
    visits: VisitsOut
    load: list[WeekdayLoadOut]
    new_clients: int
    # Больше всего занятий в этом месяце
    top: list[ClientVisitsOut]
    # Сейчас, без привязки к месяцу: давно не были и не записаны
    lapsed: list[LapsedOut]


@router.get("")
async def get_stats(
    trainer: CurrentTrainer, session: SessionDep, month: MonthQuery = None
) -> StatsOut:
    data = await stats.month_stats(
        session, trainer, month_or_current(trainer, month), datetime.now(UTC)
    )
    v = data.visits
    return StatsOut(
        month=data.month,
        visits=VisitsOut(
            attended=v.attended,
            missed_charged=v.missed_charged,
            missed_free=v.missed_free,
            unmarked=v.unmarked,
            upcoming=v.upcoming,
            cancelled_by_client=v.cancelled_by_client,
            cancelled_by_trainer=v.cancelled_by_trainer,
        ),
        load=[
            WeekdayLoadOut(
                weekday=item.weekday,
                open_minutes=item.open_minutes,
                booked_minutes=item.booked_minutes,
            )
            for item in data.load
        ],
        new_clients=data.new_clients,
        top=[ClientVisitsOut(client=PersonOut.of(t.user), sessions=t.sessions) for t in data.top],
        lapsed=[LapsedOut(client=PersonOut.of(x.user), last_at=x.last_at) for x in data.lapsed],
    )
