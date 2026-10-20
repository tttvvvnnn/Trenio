"""Клиенты в админке: поиск, карточка с историей и удаление данных по запросу."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_admin import get
from tests.test_bookings import new_client, setup_trainer, trainer_row
from tests.test_finance import booking_at
from tests.test_packages import client_id_of
from tests.test_schedule_api import second_trainer
from trenio.db.models import AdminAuditEntry, Booking, User
from trenio.services import admin_stats
from trenio.services.clients import link_client
from trenio.services.privacy import DELETED_NAME


async def test_search_and_card(client: AsyncClient, session: AsyncSession) -> None:
    headers, trainer_id, service_id = await setup_trainer(client, price=2500)
    anna = await client_id_of(client, await new_client(client, session, trainer_id, 501))
    boris = await client_id_of(client, await new_client(client, session, trainer_id, 502))
    now = datetime.now(UTC).replace(microsecond=0)
    past = await booking_at(session, trainer_id, anna, service_id, now - timedelta(days=2))
    await booking_at(session, trainer_id, anna, service_id, now + timedelta(days=3))
    attended = await session.get(Booking, past)
    assert attended is not None
    attended.attendance = "attended"
    await admin_stats.mark_active(session, anna, now)
    await session.commit()

    rows = await get(client, headers, "clients")
    # Админ сам себе не клиент: в списке только Анна и Борис, свежие сверху
    assert [r["id"] for r in rows] == [boris, anna]
    row = next(r for r in rows if r["id"] == anna)
    assert (row["bookings"], row["attended"], row["active_days"]) == (2, 1, 1)
    assert row["trainers"] == [{"id": trainer_id, "name": "Иван"}]
    assert row["last_booking_at"] is not None and row["next_booking_at"] is not None

    user = await session.get(User, anna)
    assert user is not None
    found = await get(client, headers, f"clients?q={user.first_name}")
    assert anna in [r["id"] for r in found]
    assert [r["id"] for r in await get(client, headers, "clients?q=501")] == [anna]
    # Поиск по имени тренера находит всех его клиентов
    assert len(await get(client, headers, "clients?q=иван")) == 2
    assert await get(client, headers, "clients?q=нет такого") == []

    card = await get(client, headers, f"clients/{anna}")
    assert card["telegram_id"] == 501 and card["is_trainer"] is False
    assert [h["status"] for h in card["history"]] == ["confirmed", "confirmed"]
    assert card["links"][0]["attended"] == 1
    assert card["activity"][-1] is True and len(card["activity"]) == 30

    response = await client.get("/api/admin/clients/999999", headers=headers)
    assert response.status_code == 404


async def test_delete_on_request(client: AsyncClient, session: AsyncSession) -> None:
    headers, trainer_id, service_id = await setup_trainer(client, price=2500)
    anna = await client_id_of(client, await new_client(client, session, trainer_id, 501))
    now = datetime.now(UTC).replace(microsecond=0)
    upcoming = await booking_at(session, trainer_id, anna, service_id, now + timedelta(days=1))

    url = f"/api/admin/clients/{anna}/delete"
    response = await client.post(url, headers=headers, json={"reason": "  "})
    assert response.status_code == 422
    response = await client.post(url, headers=headers, json={"reason": "письмо 20.10"})
    assert response.status_code == 204, response.text

    session.expire_all()
    user = await session.get(User, anna)
    assert user is not None and user.first_name == DELETED_NAME and user.telegram_id is None
    booking = await session.get(Booking, upcoming)
    assert booking is not None and booking.status == "cancelled"

    entry = await session.scalar(
        select(AdminAuditEntry).where(AdminAuditEntry.action == "client.deleted")
    )
    assert entry is not None
    assert entry.target == f"user:{anna}" and entry.payload["reason"] == "письмо 20.10"
    assert entry.payload["trainers"] == ["Иван"]

    # Удалённые не в общем списке, но находятся по флагу; второй раз удалить нельзя
    assert await get(client, headers, "clients") == []
    assert [r["id"] for r in await get(client, headers, "clients?deleted=true")] == [anna]
    response = await client.post(url, headers=headers, json={"reason": "ещё раз"})
    assert response.status_code == 409


async def test_trainer_is_not_deleted_as_client(client: AsyncClient, session: AsyncSession) -> None:
    headers, trainer_id, _ = await setup_trainer(client)
    # Второй тренер записался к админу: он клиент, но удалять его нужно как тренера
    other = await client_id_of(client, await second_trainer(client, session))
    user = await session.get(User, other)
    assert user is not None
    await link_client(session, user, (await trainer_row(session, trainer_id)).invite_code)

    card = await get(client, headers, f"clients/{other}")
    assert card["is_trainer"] is True
    response = await client.post(
        f"/api/admin/clients/{other}/delete", headers=headers, json={"reason": "тест"}
    )
    assert response.status_code == 409


async def test_trainer_actions_are_audited(client: AsyncClient, session: AsyncSession) -> None:
    headers, _, _ = await setup_trainer(client)
    other = await second_trainer(client, session)
    other_id = (await client.get("/api/me", headers=other)).json()["trainer"]["id"]
    response = await client.post(
        f"/api/admin/trainers/{other_id}/active", headers=headers, json={"active": False}
    )
    assert response.status_code == 204
    entry = await session.scalar(
        select(AdminAuditEntry).where(AdminAuditEntry.action == "trainer.disabled")
    )
    # Из Mini App: без входа в веб-админку
    assert entry is not None and entry.target == f"trainer:{other_id}"
    assert entry.session_id is None
