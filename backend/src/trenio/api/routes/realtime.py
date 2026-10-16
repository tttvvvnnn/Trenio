"""WebSocket /api/ws: сигнал «данные поменялись» для открытого приложения.

Браузер не даёт поставить заголовок Authorization на WebSocket, а токен в адресе
попал бы в логи nginx. Поэтому токен приходит первым сообщением: {"token": "..."}.
Дальше сервер только пишет: {"type": "ready"} после входа и {"type": "changed"},
когда у тренера, к которому относится человек, что-то поменялось.

Закрытие с кодом 4401 — токен не подошёл, переподключаться без нового входа незачем.
Живо ли соединение, проверяет uvicorn: раз в 20 секунд шлёт ping. Эти же ping
не дают nginx закрыть «молчащее» соединение по таймауту.
"""

import asyncio
import contextlib
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from trenio.auth.tokens import TokenError, decode_access_token
from trenio.config import get_settings
from trenio.db.models import TrainerClient
from trenio.db.session import get_sessionmaker
from trenio.realtime import HubFull, hub
from trenio.services.trainers import get_active_trainer
from trenio.services.users import get_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["realtime"])

AUTH_TIMEOUT_S = 10
UNAUTHORIZED = 4401


async def _authenticate(websocket: WebSocket) -> int | None:
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), AUTH_TIMEOUT_S)
        token = json.loads(raw)["token"]
        return decode_access_token(str(token), get_settings().jwt_secret.get_secret_value())
    except (TimeoutError, ValueError, KeyError, TypeError, TokenError):
        return None


async def _trainer_ids(user_id: int) -> set[int] | None:
    """Тренеры, чьи изменения касаются человека: он сам и те, у кого он клиент."""
    # Своя короткая сессия: соединение живёт долго, держать подключение к базе нельзя
    async with get_sessionmaker()() as session:
        user = await get_user(session, user_id)
        if user is None or user.is_deleted:
            return None
        ids = set(
            await session.scalars(
                select(TrainerClient.trainer_id).where(TrainerClient.user_id == user_id)
            )
        )
        trainer = await get_active_trainer(session, user_id)
        if trainer is not None:
            ids.add(trainer.id)
        return ids


async def _until_closed(websocket: WebSocket) -> None:
    # Клиент сам ничего не шлёт; читаем, только чтобы заметить закрытие
    with contextlib.suppress(WebSocketDisconnect):
        while True:
            await websocket.receive_text()


@router.websocket("/ws")
async def updates(websocket: WebSocket) -> None:
    await websocket.accept()
    user_id = await _authenticate(websocket)
    trainer_ids = None if user_id is None else await _trainer_ids(user_id)
    if trainer_ids is None:
        await websocket.close(UNAUTHORIZED)
        return
    try:
        with hub.subscribe(trainer_ids) as queue:
            await websocket.send_json({"type": "ready"})
            closed = asyncio.create_task(_until_closed(websocket))
            try:
                while True:
                    signal = asyncio.create_task(queue.get())
                    done, _ = await asyncio.wait(
                        {signal, closed}, return_when=asyncio.FIRST_COMPLETED
                    )
                    if closed in done:
                        signal.cancel()
                        return
                    await websocket.send_json({"type": "changed"})
            finally:
                closed.cancel()
    except HubFull:
        logger.warning("Realtime: достигнут предел соединений")
        await websocket.close(status.WS_1013_TRY_AGAIN_LATER)
    except WebSocketDisconnect:
        pass
