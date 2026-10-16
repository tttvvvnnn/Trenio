"""Живые обновления: открытое приложение узнаёт, что его данные поменялись.

Сервер шлёт не сами данные, а сигнал «у этого тренера что-то поменялось»;
приложение перечитывает текущий экран обычными запросами, и права проверяются там же.
Сигнал получают сам тренер и все его клиенты: клиенту важны свободные окошки,
которые меняют записи других людей.

Подписки живут в памяти процесса: API, бот и планировщик сейчас работают в одном
процессе, поэтому изменение из любого из них доходит до открытых соединений.
Если части разъедутся по контейнерам, publish переедет на PostgreSQL LISTEN/NOTIFY.

Что поменялось, отслеживаем по сессии SQLAlchemy: после flush запоминаем тренеров
изменённых строк, после commit шлём сигнал, после rollback забываем.
Поэтому новые сервисы ничего вызывать не должны. Исключение — массовые
UPDATE/DELETE мимо ORM-объектов: там нужно вызвать mark() самому.
"""

import asyncio
import logging
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from itertools import chain
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import instance_dict
from sqlalchemy.orm.util import identity_key

from trenio.db.models import (
    ClientMeasurement,
    Package,
    PackageSession,
    Payment,
    Trainer,
    TrainerClient,
)

logger = logging.getLogger(__name__)

# Защита памяти маленького сервера: на бету с запасом
MAX_CONNECTIONS = 1000

_PENDING = "realtime_trainers"


class HubFull(Exception):
    """Соединений слишком много: новое лучше закрыть, приложение обойдётся без сигналов."""


class Hub:
    """Открытые соединения по тренерам. У соединения очередь на один сигнал:
    сигналы одинаковые, поэтому несколько подряд схлопываются в один."""

    def __init__(self) -> None:
        self._topics: dict[int, set[asyncio.Queue[None]]] = {}
        self._count = 0

    @property
    def connections(self) -> int:
        return self._count

    @contextmanager
    def subscribe(self, trainer_ids: Iterable[int]) -> Iterator[asyncio.Queue[None]]:
        if self._count >= MAX_CONNECTIONS:
            raise HubFull
        queue: asyncio.Queue[None] = asyncio.Queue(maxsize=1)
        topics = set(trainer_ids)
        for trainer_id in topics:
            self._topics.setdefault(trainer_id, set()).add(queue)
        self._count += 1
        try:
            yield queue
        finally:
            self._count -= 1
            for trainer_id in topics:
                subscribers = self._topics.get(trainer_id)
                if subscribers is None:
                    continue
                subscribers.discard(queue)
                if not subscribers:
                    del self._topics[trainer_id]

    def publish(self, trainer_ids: Iterable[int]) -> None:
        queues = set(chain.from_iterable(self._topics.get(t, ()) for t in set(trainer_ids)))
        for queue in queues:
            if queue.empty():
                queue.put_nowait(None)


hub = Hub()


def mark(session: AsyncSession | Session, trainer_id: int) -> None:
    """Отметить, что у тренера поменялись данные; сигнал уйдёт после commit."""
    sync = session.sync_session if isinstance(session, AsyncSession) else session
    sync.info.setdefault(_PENDING, set()).add(trainer_id)


def _cached(session: Session, model: type[Any], pk: Any) -> Any:
    # Только из уже загруженного: внутри flush в базу не ходим
    return None if pk is None else session.identity_map.get(identity_key(model, pk))


def _trainer_of(session: Session, obj: object) -> int | None:
    if isinstance(obj, Trainer):
        return obj.id
    values = instance_dict(obj)
    if "trainer_id" in values:
        return int(values["trainer_id"])
    parent: Any = None
    if isinstance(obj, PackageSession | Payment):
        parent = _cached(session, Package, values.get("package_id"))
    elif isinstance(obj, ClientMeasurement):
        parent = _cached(session, TrainerClient, values.get("trainer_client_id"))
    return None if parent is None else int(parent.trainer_id)


@event.listens_for(Session, "after_flush")
def _collect(session: Session, _: Any) -> None:
    # После flush списки new/dirty/deleted ещё показывают то, что ушло в базу
    for obj in chain(session.new, session.dirty, session.deleted):
        if obj in session.dirty and not session.is_modified(obj, include_collections=False):
            continue
        trainer_id = _trainer_of(session, obj)
        if trainer_id is not None:
            mark(session, trainer_id)


@event.listens_for(Session, "after_commit")
def _publish(session: Session) -> None:
    trainer_ids = session.info.pop(_PENDING, None)
    if trainer_ids:
        hub.publish(trainer_ids)


@event.listens_for(Session, "after_rollback")
def _forget(session: Session) -> None:
    session.info.pop(_PENDING, None)
