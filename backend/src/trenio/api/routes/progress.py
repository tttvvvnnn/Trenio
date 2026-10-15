"""Прогресс клиента: замеры. Тренер записывает, клиент смотрит."""

from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from trenio.api.deps import CurrentTrainer, CurrentUser, SessionDep
from trenio.services import progress
from trenio.services.progress import NewMeasurement, ProgressError, ProgressRejected

router = APIRouter(tags=["progress"])

_ERRORS = {
    ProgressError.NOT_CLIENT: (404, "Клиент не найден."),
    ProgressError.NOT_FOUND: (404, "Замер не найден."),
    ProgressError.BAD_KIND: (422, "Укажите, что измеряли."),
}


def progress_error(rejected: ProgressRejected) -> HTTPException:
    code, message = _ERRORS[rejected.reason]
    return HTTPException(code, message)


class PointOut(BaseModel):
    id: int
    day: date
    value: float


class SeriesOut(BaseModel):
    key: str
    kind: str
    label: str
    unit: str | None
    # Старые первыми
    points: list[PointOut]

    @classmethod
    def of(cls, item: progress.Series) -> "SeriesOut":
        return cls(
            key=item.key,
            kind=item.kind,
            label=item.label,
            unit=item.unit,
            points=[PointOut(id=p.id, day=p.day, value=float(p.value)) for p in item.points],
        )


def _out(found: list[progress.Series]) -> list[SeriesOut]:
    return [SeriesOut.of(item) for item in found]


class MeasurementIn(BaseModel):
    day: date
    # weight, waist, chest, hips или custom
    kind: str = Field(max_length=16)
    value: Annotated[Decimal, Field(gt=0, lt=100000, max_digits=8, decimal_places=2)]
    # Только для своего вида
    label: str | None = Field(default=None, max_length=48)
    unit: str | None = Field(default=None, max_length=16)


@router.get("/trainer/clients/{client_id}/progress")
async def get_progress(
    client_id: int, trainer: CurrentTrainer, session: SessionDep
) -> list[SeriesOut]:
    try:
        return _out(await progress.client_progress(session, trainer, client_id))
    except ProgressRejected as rejected:
        raise progress_error(rejected) from None


@router.post("/trainer/clients/{client_id}/measurements")
async def add_measurement(
    client_id: int, body: MeasurementIn, trainer: CurrentTrainer, session: SessionDep
) -> list[SeriesOut]:
    """Новый замер. Тот же вид в тот же день заменяет прежнее значение."""
    new = NewMeasurement(body.day, body.kind, body.value, body.label, body.unit)
    try:
        return _out(await progress.add_measurement(session, trainer, client_id, new))
    except ProgressRejected as rejected:
        raise progress_error(rejected) from None


@router.delete("/trainer/clients/{client_id}/measurements/{measurement_id}")
async def delete_measurement(
    client_id: int, measurement_id: int, trainer: CurrentTrainer, session: SessionDep
) -> list[SeriesOut]:
    try:
        found = await progress.delete_measurement(session, trainer, client_id, measurement_id)
    except ProgressRejected as rejected:
        raise progress_error(rejected) from None
    return _out(found)


class TrainerProgressOut(BaseModel):
    trainer_id: int
    trainer_name: str
    series: list[SeriesOut]


@router.get("/client/progress")
async def my_progress(user: CurrentUser, session: SessionDep) -> list[TrainerProgressOut]:
    """Замеры клиента у всех тренеров, только чтение."""
    return [
        TrainerProgressOut(
            trainer_id=item.trainer.id,
            trainer_name=item.trainer.display_name,
            series=_out(item.series),
        )
        for item in await progress.my_progress(session, user)
    ]
