"""Персональные данные: согласие, телефон клиента, удаление аккаунта."""

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_bookings import book, me_id, new_client, setup_trainer
from tests.test_offline_clients import add_client, bot_username, trainer_books
from tests.test_packages import sell
from tests.test_schedule_api import auth
from trenio.db.models import Booking, Notification, Package, Service, Trainer, User
from trenio.services.privacy import DELETED_NAME, POLICY_VERSION, normalize_phone

__all__ = ["bot_username"]

NEXT_MONDAY = "2030-01-14T07:00:00Z"


async def test_policy_is_public(client: AsyncClient) -> None:
    response = await client.get("/api/privacy")
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == POLICY_VERSION
    assert "Политика обработки персональных данных" in body["text"]


async def test_consent_asked_once_per_version(client: AsyncClient, session: AsyncSession) -> None:
    headers = await auth(client, 5005)
    assert (await client.get("/api/me", headers=headers)).json()["consent_required"] is True
    response = await client.post("/api/me/consent", headers=headers)
    assert response.status_code == 204
    assert (await client.get("/api/me", headers=headers)).json()["consent_required"] is False

    # Политику поменяли: старое согласие не считается
    user = await session.scalar(select(User).where(User.telegram_id == 5005))
    assert user is not None
    user.consent_version = POLICY_VERSION - 1
    await session.commit()
    assert (await client.get("/api/me", headers=headers)).json()["consent_required"] is True


def test_normalize_phone() -> None:
    assert normalize_phone("8 (912) 345-67-89") == "+79123456789"
    assert normalize_phone("+7 912 345 67 89") == "+79123456789"
    assert normalize_phone("9123456789") == "+79123456789"
    assert normalize_phone("+49 30 1234567") == "+49301234567"


async def test_phone_needs_consent_and_client_can_remove_it(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers, trainer_id, _ = await setup_trainer(client)
    client_headers = await new_client(client, session, trainer_id, 3003)
    client_id = await me_id(client, client_headers)
    url = f"/api/trainer/clients/{client_id}/phone"

    no_consent = await client.put(url, headers=headers, json={"phone": "89123456789"})
    assert no_consent.status_code == 422
    bad = await client.put(url, headers=headers, json={"phone": "12", "consent": True})
    assert bad.status_code == 422
    saved = await client.put(url, headers=headers, json={"phone": "89123456789", "consent": True})
    assert saved.json() == {"phone": "+79123456789"}
    card = (await client.get(f"/api/trainer/clients/{client_id}", headers=headers)).json()
    assert card["phone"] == "+79123456789"

    trainers = (await client.get("/api/client/trainers", headers=client_headers)).json()
    assert trainers[0]["my_phone"] == "+79123456789"
    removed = await client.delete(
        f"/api/client/trainers/{trainer_id}/phone", headers=client_headers
    )
    assert removed.status_code == 204
    card = (await client.get(f"/api/trainer/clients/{client_id}", headers=headers)).json()
    assert card["phone"] is None


async def test_deleted_client_stays_anonymous_in_trainer_records(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers, trainer_id, service_id = await setup_trainer(client)
    client_headers = await new_client(client, session, trainer_id, 3003)
    client_id = await me_id(client, client_headers)
    await sell(client, headers, client_id)
    status_code, _ = await book(client, client_headers, trainer_id, service_id)
    assert status_code == 201
    await client.put(
        f"/api/trainer/clients/{client_id}/notes", headers=headers, json={"notes": "колено"}
    )

    response = await client.delete("/api/me", headers=client_headers)
    assert response.status_code == 204
    # Старый токен больше не пускает
    assert (await client.get("/api/me", headers=client_headers)).status_code == 401

    session.expire_all()
    user = await session.get(User, client_id)
    assert user is not None
    assert (user.telegram_id, user.first_name, user.username) == (None, DELETED_NAME, None)
    assert user.deleted_at is not None
    # Блок остаётся у тренера, будущая запись отменена, тренеру ушло «клиент отменил»
    assert await session.scalar(select(func.count()).select_from(Package)) == 1
    booking = await session.scalar(select(Booking))
    assert booking is not None
    assert (booking.status, booking.cancelled_by) == ("cancelled", "client")
    kinds = (await session.scalars(select(Notification.kind))).all()
    assert "client_cancelled" in kinds

    card = (await client.get(f"/api/trainer/clients/{client_id}", headers=headers)).json()
    assert card["notes"] is None
    assert (card["client"]["deleted"], card["client"]["offline"]) == (True, False)
    next_week = {"client_id": client_id, "service_id": service_id, "starts_at": NEXT_MONDAY}
    booked = await client.post("/api/trainer/bookings", headers=headers, json=next_week)
    assert booked.status_code != 201

    # Тот же человек снова заходит из Telegram: это новый аккаунт, без старой истории
    again = await auth(client, 3003)
    assert await me_id(client, again) != client_id


async def test_client_without_records_is_deleted_completely(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await auth(client, 5005)
    user_id = await me_id(client, headers)
    assert (await client.delete("/api/me", headers=headers)).status_code == 204
    session.expire_all()
    assert await session.get(User, user_id) is None


async def test_deleted_trainer_takes_their_data(client: AsyncClient, session: AsyncSession) -> None:
    headers, trainer_id, service_id = await setup_trainer(client)
    trainer_user_id = await me_id(client, headers)
    offline = await add_client(client, headers)
    await trainer_books(client, headers, offline["id"], service_id)
    client_headers = await new_client(client, session, trainer_id, 3003)
    client_id = await me_id(client, client_headers)

    assert (await client.delete("/api/me", headers=headers)).status_code == 204
    session.expire_all()
    assert await session.get(Trainer, trainer_id) is None
    assert await session.get(User, offline["id"]) is None
    assert await session.scalar(select(func.count()).select_from(Service)) == 0
    assert await session.scalar(select(func.count()).select_from(Booking)) == 0
    assert await session.get(User, trainer_user_id) is None
    # Клиент с Telegram остался, просто без этого тренера
    assert await session.get(User, client_id) is not None
    assert (await client.get("/api/client/trainers", headers=client_headers)).json() == []
