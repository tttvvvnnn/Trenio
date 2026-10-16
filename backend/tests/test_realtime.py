"""Живые обновления по WebSocket: кто получает сигнал «данные поменялись»."""

import asyncio
import json
from collections.abc import AsyncIterator, MutableMapping
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_bookings import TEN, book, new_client, setup_trainer
from tests.test_schedule_api import Headers, auth
from trenio.api.app import Component, create_app
from trenio.realtime import hub

CLIENT_TG = 5001
STRANGER_TG = 5002


class Socket:
    """WebSocket-клиент прямо поверх ASGI: в том же цикле событий, что и база тестов."""

    def __init__(self, app: FastAPI) -> None:
        self.app = app
        self.incoming: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.outgoing: asyncio.Queue[MutableMapping[str, Any]] = asyncio.Queue()
        scope = {
            "type": "websocket",
            "asgi": {"version": "3.0"},
            "path": "/api/ws",
            "raw_path": b"/api/ws",
            "root_path": "",
            "scheme": "ws",
            "query_string": b"",
            "headers": [],
            "client": ("test", 1),
            "server": ("test", 80),
            "subprotocols": [],
        }
        self.task = asyncio.create_task(app(scope, self.incoming.get, self.outgoing.put))

    async def receive(self, timeout: float = 2) -> MutableMapping[str, Any]:
        return await asyncio.wait_for(self.outgoing.get(), timeout)

    async def silent(self, timeout: float = 0.2) -> bool:
        try:
            await asyncio.wait_for(self.outgoing.get(), timeout)
        except TimeoutError:
            return True
        return False

    async def send(self, data: object) -> None:
        await self.incoming.put({"type": "websocket.receive", "text": json.dumps(data)})

    async def close(self) -> None:
        await self.incoming.put({"type": "websocket.disconnect", "code": 1000})
        await asyncio.wait_for(self.task, 2)


@pytest.fixture
def app(clean_db: None) -> FastAPI:
    return create_app(frozenset({Component.API}))


@asynccontextmanager
async def connect(app: FastAPI, headers: Headers) -> AsyncIterator[Socket]:
    socket = Socket(app)
    await socket.incoming.put({"type": "websocket.connect"})
    assert (await socket.receive())["type"] == "websocket.accept"
    await socket.send({"token": headers["Authorization"].removeprefix("Bearer ")})
    assert json.loads((await socket.receive())["text"]) == {"type": "ready"}
    try:
        yield socket
    finally:
        await socket.close()


def is_changed(message: MutableMapping[str, Any]) -> bool:
    if message["type"] != "websocket.send":
        return False
    return bool(json.loads(message["text"]) == {"type": "changed"})


async def test_bad_token_closes_with_4401(app: FastAPI) -> None:
    socket = Socket(app)
    await socket.incoming.put({"type": "websocket.connect"})
    assert (await socket.receive())["type"] == "websocket.accept"
    await socket.send({"token": "nope"})
    assert await socket.receive() == {"type": "websocket.close", "code": 4401, "reason": ""}
    await asyncio.wait_for(socket.task, 2)


async def test_booking_signals_trainer_and_clients_only(
    app: FastAPI, client: AsyncClient, session: AsyncSession
) -> None:
    trainer_headers, trainer_id, service_id = await setup_trainer(client)
    client_headers = await new_client(client, session, trainer_id, CLIENT_TG)
    stranger_headers = await auth(client, STRANGER_TG)

    async with (
        connect(app, trainer_headers) as trainer,
        connect(app, client_headers) as customer,
        connect(app, stranger_headers) as stranger,
    ):
        assert hub.connections == 3
        status, _ = await book(client, client_headers, trainer_id, service_id)
        assert status == 201
        assert is_changed(await trainer.receive())
        assert is_changed(await customer.receive())
        assert await stranger.silent()

        # Отказ ничего не меняет — и сигнала нет
        status, _ = await book(client, client_headers, trainer_id, service_id, TEN)
        assert status == 409
        assert await trainer.silent()
    assert hub.connections == 0


async def test_bulk_schedule_reset_signals(
    app: FastAPI, client: AsyncClient, session: AsyncSession
) -> None:
    trainer_headers, trainer_id, _ = await setup_trainer(client)
    client_headers = await new_client(client, session, trainer_id, CLIENT_TG)
    async with connect(app, client_headers) as customer:
        response = await client.post(
            "/api/trainer/schedule/days/reset",
            headers=trainer_headers,
            json={"days": ["2030-01-07"]},
        )
        assert response.status_code == 204, response.text
        assert is_changed(await customer.receive())
