"""Прогресс клиента: замеры у тренера и заметки к занятиям.

Замеры живут в паре тренер–клиент: тренер записывает, клиент только смотрит.
Один замер вида в день: повторный ввод за тот же день заменяет значение.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.db.models import Booking, ClientMeasurement, Trainer, TrainerClient, User

# Встроенные виды: название и единица. Порядок — как показываем
KINDS: dict[str, tuple[str, str]] = {
    "weight": ("Вес", "кг"),
    "waist": ("Талия", "см"),
    "chest": ("Грудь", "см"),
    "hips": ("Бёдра", "см"),
}
CUSTOM = "custom"

MAX_NOTE = 2000


class ProgressError(StrEnum):
    NOT_CLIENT = "not_client"
    NOT_FOUND = "not_found"
    # Свой вид без названия или неизвестный вид
    BAD_KIND = "bad_kind"


class ProgressRejected(Exception):
    def __init__(self, reason: ProgressError) -> None:
        super().__init__(reason.value)
        self.reason = reason


@dataclass(frozen=True)
class Point:
    id: int
    day: date
    value: Decimal


@dataclass(frozen=True)
class Series:
    # weight, waist… или custom:<название в нижнем регистре>
    key: str
    kind: str
    label: str
    unit: str | None
    # Старые первыми
    points: list[Point]


@dataclass(frozen=True)
class NewMeasurement:
    day: date
    kind: str
    value: Decimal
    label: str | None = None
    unit: str | None = None


def _label(item: ClientMeasurement) -> str:
    return KINDS[item.kind][0] if item.kind in KINDS else (item.label or "")


def _unit(item: ClientMeasurement) -> str | None:
    return KINDS[item.kind][1] if item.kind in KINDS else item.unit


def _key(kind: str, label: str | None) -> str:
    return kind if kind in KINDS else f"{CUSTOM}:{(label or '').strip().lower()}"


def series(measurements: Sequence[ClientMeasurement]) -> list[Series]:
    """Замеры по видам: сначала встроенные в их порядке, потом свои по названию."""
    grouped: dict[str, list[ClientMeasurement]] = {}
    for item in sorted(measurements, key=lambda m: (m.day, m.id)):
        grouped.setdefault(_key(item.kind, item.label), []).append(item)
    order = list(KINDS)

    def rank(key: str) -> tuple[int, str]:
        return (order.index(key), "") if key in KINDS else (len(order), key)

    result = []
    for key in sorted(grouped, key=rank):
        items = grouped[key]
        # Название и единицу своего вида берём из последнего замера
        last = items[-1]
        result.append(
            Series(
                key=key,
                kind=last.kind,
                label=_label(last),
                unit=_unit(last),
                points=[Point(m.id, m.day, m.value) for m in items],
            )
        )
    return result


async def _link(session: AsyncSession, trainer: Trainer, client_id: int) -> TrainerClient:
    link = await session.scalar(
        select(TrainerClient).where(
            TrainerClient.trainer_id == trainer.id, TrainerClient.user_id == client_id
        )
    )
    if link is None:
        raise ProgressRejected(ProgressError.NOT_CLIENT)
    return link


async def _measurements(session: AsyncSession, link_ids: Sequence[int]) -> list[ClientMeasurement]:
    if not link_ids:
        return []
    found = await session.scalars(
        select(ClientMeasurement).where(ClientMeasurement.trainer_client_id.in_(link_ids))
    )
    return list(found.all())


async def client_progress(session: AsyncSession, trainer: Trainer, client_id: int) -> list[Series]:
    link = await _link(session, trainer, client_id)
    return series(await _measurements(session, [link.id]))


async def add_measurement(
    session: AsyncSession, trainer: Trainer, client_id: int, new: NewMeasurement
) -> list[Series]:
    link = await _link(session, trainer, client_id)
    if link.user.is_deleted:
        raise ProgressRejected(ProgressError.NOT_CLIENT)
    label = (new.label or "").strip() or None
    unit = (new.unit or "").strip() or None
    if new.kind == CUSTOM:
        if label is None:
            raise ProgressRejected(ProgressError.BAD_KIND)
    elif new.kind in KINDS:
        label = unit = None
    else:
        raise ProgressRejected(ProgressError.BAD_KIND)

    key = _key(new.kind, label)
    same_day = [
        item
        for item in await _measurements(session, [link.id])
        if item.day == new.day and _key(item.kind, item.label) == key
    ]
    if same_day:
        item = same_day[0]
        item.value = new.value
        item.label = label
        item.unit = unit
    else:
        session.add(
            ClientMeasurement(
                trainer_client_id=link.id,
                day=new.day,
                kind=new.kind,
                label=label,
                unit=unit,
                value=new.value,
            )
        )
    await session.commit()
    return await client_progress(session, trainer, client_id)


async def delete_measurement(
    session: AsyncSession, trainer: Trainer, client_id: int, measurement_id: int
) -> list[Series]:
    link = await _link(session, trainer, client_id)
    item = await session.get(ClientMeasurement, measurement_id)
    if item is None or item.trainer_client_id != link.id:
        raise ProgressRejected(ProgressError.NOT_FOUND)
    await session.delete(item)
    await session.commit()
    return await client_progress(session, trainer, client_id)


@dataclass(frozen=True)
class TrainerProgress:
    trainer: Trainer
    series: list[Series]


async def my_progress(session: AsyncSession, user: User) -> list[TrainerProgress]:
    """Прогресс клиента у всех тренеров, у которых есть замеры."""
    links = (
        await session.scalars(
            select(TrainerClient)
            .join(TrainerClient.trainer)
            .where(TrainerClient.user_id == user.id, Trainer.is_active.is_(True))
            .order_by(Trainer.display_name, Trainer.id)
        )
    ).all()
    found = await _measurements(session, [link.id for link in links])
    result = []
    for link in links:
        own = [item for item in found if item.trainer_client_id == link.id]
        if own:
            result.append(TrainerProgress(link.trainer, series(own)))
    return result


async def set_note(
    session: AsyncSession, booking: Booking, note: str | None, private: bool
) -> Booking:
    note = (note or "").strip() or None
    booking.trainer_note = note
    booking.trainer_note_private = private and note is not None
    await session.commit()
    return booking


async def forget(session: AsyncSession, user: User) -> None:
    """Удаление аккаунта: замеры и заметки к занятиям этого человека больше не храним."""
    links = select(TrainerClient.id).where(TrainerClient.user_id == user.id).scalar_subquery()
    await session.execute(
        delete(ClientMeasurement).where(ClientMeasurement.trainer_client_id.in_(links))
    )
    for booking in (
        await session.scalars(
            select(Booking).where(Booking.client_id == user.id, Booking.trainer_note.is_not(None))
        )
    ).all():
        booking.trainer_note = None
        booking.trainer_note_private = False
