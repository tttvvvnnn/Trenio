"""Рассылки тренерам из админки: кому отправить, постановка в очередь и доставка.

Сообщения идут через обычную очередь notifications: тот же отправщик, повторы при сбоях
и отметка failed, если тренер заблокировал бота. Админы рассылку не получают, себе
админ отправляет тестовое сообщение.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.db.models import Broadcast, Notification, Trainer
from trenio.services import admin_stats, notifications, subscription
from trenio.services.admin_stats import TrainerRow, TrainerState

HISTORY_LIMIT = 20


class Segment(StrEnum):
    ALL = "all"
    PRO = "pro"
    TRIAL = "trial"
    FREE = "free"
    NOT_SET_UP = "not_set_up"
    QUIET = "quiet"


def _matches(row: TrainerRow, segment: Segment, now: datetime) -> bool:
    if row.state is TrainerState.DISABLED or subscription.is_admin_trainer(row.trainer):
        return False
    if row.trainer.user.telegram_id is None:
        return False
    match segment:
        case Segment.ALL:
            return True
        case Segment.NOT_SET_UP | Segment.QUIET:
            return row.state.value == segment.value
        case _:
            return subscription.state_of(row.trainer, now).value == segment.value


async def audience(session: AsyncSession, segment: Segment, now: datetime) -> list[Trainer]:
    rows = await admin_stats.trainer_rows(session, now)
    trainers = [row.trainer for row in rows if _matches(row, segment, now)]
    return sorted(trainers, key=lambda t: t.display_name)


async def send(
    session: AsyncSession,
    text: str,
    segment: Segment,
    with_button: bool,
    created_by: int,
    now: datetime,
) -> Broadcast:
    """Ставит рассылку в очередь. Коммит за вызывающим: вместе с записью в журнал."""
    trainers = await audience(session, segment, now)
    item = Broadcast(
        text=text,
        segment=segment.value,
        with_button=with_button,
        recipients=len(trainers),
        created_by=created_by,
        created_at=now,
    )
    session.add(item)
    await session.flush()
    for trainer in trainers:
        await notifications.broadcast(session, item.id, trainer.user_id, now)
    return item


@dataclass(frozen=True, slots=True)
class Delivery:
    broadcast: Broadcast
    sent: int
    failed: int
    pending: int


async def history(session: AsyncSession) -> list[Delivery]:
    items: Sequence[Broadcast] = (
        await session.scalars(
            select(Broadcast).order_by(Broadcast.created_at.desc()).limit(HISTORY_LIMIT)
        )
    ).all()
    if not items:
        return []
    broadcast_id = Notification.payload["broadcast_id"].as_integer()
    counts: dict[int, dict[str, int]] = {}
    rows = await session.execute(
        select(broadcast_id, Notification.status, func.count())
        .where(
            Notification.kind == notifications.Kind.BROADCAST.value,
            broadcast_id.in_([item.id for item in items]),
        )
        .group_by(broadcast_id, Notification.status)
    )
    for item_id, status, count in rows.all():
        counts.setdefault(item_id, {})[status] = count
    result = []
    for item in items:
        by_status = counts.get(item.id, {})
        result.append(
            Delivery(
                broadcast=item,
                sent=by_status.get(notifications.Status.SENT.value, 0),
                failed=by_status.get(notifications.Status.FAILED.value, 0)
                + by_status.get(notifications.Status.SKIPPED.value, 0),
                pending=by_status.get(notifications.Status.PENDING.value, 0),
            )
        )
    return result
