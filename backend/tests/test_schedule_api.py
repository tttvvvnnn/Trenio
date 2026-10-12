"""Услуги, шаблон, исключения и окошки через API."""

from datetime import timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import ADMIN_TELEGRAM_ID
from tests.factories import make_init_data
from tests.test_api import login
from trenio.services.trainers import accept_invite, create_invite, get_trainer
from trenio.services.users import get_user

# Понедельник в будущем, чтобы окошки не отсекались как прошедшие
MONDAY = "2030-01-07"

Headers = dict[str, str]


async def auth(client: AsyncClient, telegram_id: int = ADMIN_TELEGRAM_ID) -> Headers:
    token = await login(client, make_init_data(user_id=telegram_id))
    return {"Authorization": f"Bearer {token}"}


async def second_trainer(client: AsyncClient, session: AsyncSession) -> Headers:
    """Второй тренер по приглашению от админа."""
    admin_headers = await auth(client)
    other_headers = await auth(client, 2002)
    admin_me = (await client.get("/api/me", headers=admin_headers)).json()
    other_me = (await client.get("/api/me", headers=other_headers)).json()
    admin = await get_user(session, admin_me["id"])
    other = await get_user(session, other_me["id"])
    assert admin is not None and other is not None
    invite = await create_invite(session, admin, timedelta(days=1))
    await accept_invite(session, other, invite.code)
    assert await get_trainer(session, other.id) is not None
    return other_headers


async def create_service(client: AsyncClient, headers: Headers, **fields: object) -> int:
    body = {"name": "Персональная", "duration_min": 60, **fields}
    response = await client.post("/api/trainer/services", headers=headers, json=body)
    assert response.status_code == 201, response.text
    service_id: int = response.json()["id"]
    return service_id


async def test_service_crud(client: AsyncClient) -> None:
    headers = await auth(client)
    service_id = await create_service(client, headers, capacity=2, price=2000)

    response = await client.patch(
        f"/api/trainer/services/{service_id}",
        headers=headers,
        json={"name": "Сплит", "price": None},
    )
    assert response.status_code == 200, response.text
    service = response.json()
    assert service["name"] == "Сплит"
    assert service["price"] is None
    assert service["capacity"] == 2

    await client.patch(
        f"/api/trainer/services/{service_id}", headers=headers, json={"is_active": False}
    )
    assert (await client.get("/api/trainer/services", headers=headers)).json() == []
    everything = await client.get(
        "/api/trainer/services", headers=headers, params={"include_inactive": "true"}
    )
    assert [item["id"] for item in everything.json()] == [service_id]


async def test_service_validation(client: AsyncClient) -> None:
    headers = await auth(client)
    for body in (
        {"name": "", "duration_min": 60},
        {"name": "Короткая", "duration_min": 1},
        {"name": "Группа", "duration_min": 60, "capacity": 0},
    ):
        response = await client.post("/api/trainer/services", headers=headers, json=body)
        assert response.status_code == 422, body


async def test_two_weeks_of_slots(client: AsyncClient) -> None:
    headers = await auth(client)
    service_id = await create_service(client, headers)

    for weekday in (0, 2):  # понедельник и среда, 10:00–13:00
        response = await client.post(
            "/api/trainer/schedule/rules",
            headers=headers,
            json={"weekday": weekday, "start": "10:00", "end": "13:00"},
        )
        assert response.status_code == 201, response.text

    # Среда первой недели — выходной, в субботу второй недели доп. окно
    await client.post(
        "/api/trainer/schedule/exceptions",
        headers=headers,
        json={"day": "2030-01-09", "kind": "closed"},
    )
    await client.post(
        "/api/trainer/schedule/exceptions",
        headers=headers,
        json={"day": "2030-01-19", "kind": "extra", "start": "09:00", "end": "10:00"},
    )

    response = await client.get(
        "/api/trainer/slots", headers=headers, params={"from": MONDAY, "days": 14}
    )
    assert response.status_code == 200, response.text
    found = response.json()
    days = sorted({slot["starts_at"][:10] for slot in found})
    assert days == ["2030-01-07", "2030-01-14", "2030-01-16", "2030-01-19"]
    assert len(found) == 3 + 3 + 3 + 1
    assert found[0] == {
        "service_id": service_id,
        "starts_at": "2030-01-07T07:00:00Z",
        "ends_at": "2030-01-07T08:00:00Z",
    }


async def test_rule_update_and_delete(client: AsyncClient) -> None:
    headers = await auth(client)
    personal = await create_service(client, headers)
    split = await create_service(client, headers, name="Сплит", capacity=2)

    created = await client.post(
        "/api/trainer/schedule/rules",
        headers=headers,
        json={"weekday": 0, "start": "10:00", "end": "12:00", "service_ids": [personal]},
    )
    rule = created.json()
    assert rule["service_ids"] == [personal]

    replaced = await client.put(
        f"/api/trainer/schedule/rules/{rule['id']}",
        headers=headers,
        json={"weekday": 1, "start": "18:00", "end": "20:00", "service_ids": [split]},
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["service_ids"] == [split]
    assert replaced.json()["start"] == "18:00:00"

    deleted = await client.delete(f"/api/trainer/schedule/rules/{rule['id']}", headers=headers)
    assert deleted.status_code == 204
    assert (await client.get("/api/trainer/schedule/rules", headers=headers)).json() == []


async def test_schedule_validation(client: AsyncClient) -> None:
    headers = await auth(client)
    bad_rules: tuple[dict[str, object], ...] = (
        {"weekday": 0, "start": "12:00", "end": "10:00"},
        {"weekday": 7, "start": "10:00", "end": "12:00"},
        {"weekday": 0, "start": "10:00", "end": "12:00", "service_ids": [999]},
    )
    for body in bad_rules:
        response = await client.post("/api/trainer/schedule/rules", headers=headers, json=body)
        assert response.status_code == 422, body

    bad_exceptions: tuple[dict[str, object], ...] = (
        {"day": MONDAY, "kind": "extra"},
        {"day": MONDAY, "kind": "closed", "start": "10:00"},
        {"day": MONDAY, "kind": "holiday"},
    )
    for body in bad_exceptions:
        response = await client.post("/api/trainer/schedule/exceptions", headers=headers, json=body)
        assert response.status_code == 422, body


async def test_exceptions_listing(client: AsyncClient) -> None:
    headers = await auth(client)
    for day in ("2030-01-07", "2030-02-01"):
        await client.post(
            "/api/trainer/schedule/exceptions",
            headers=headers,
            json={"day": day, "kind": "closed"},
        )
    response = await client.get(
        "/api/trainer/schedule/exceptions",
        headers=headers,
        params={"from": "2030-01-01", "to": "2030-01-31"},
    )
    listed = response.json()
    assert [item["day"] for item in listed] == ["2030-01-07"]

    deleted = await client.delete(
        f"/api/trainer/schedule/exceptions/{listed[0]['id']}", headers=headers
    )
    assert deleted.status_code == 204


async def test_trainers_cannot_touch_each_other(client: AsyncClient, session: AsyncSession) -> None:
    admin_headers = await auth(client)
    service_id = await create_service(client, admin_headers)
    rule = (
        await client.post(
            "/api/trainer/schedule/rules",
            headers=admin_headers,
            json={"weekday": 0, "start": "10:00", "end": "12:00"},
        )
    ).json()

    other = await second_trainer(client, session)
    assert (await client.get("/api/trainer/services", headers=other)).json() == []
    patched = await client.patch(
        f"/api/trainer/services/{service_id}", headers=other, json={"name": "Чужая"}
    )
    assert patched.status_code == 404
    assert (
        await client.delete(f"/api/trainer/schedule/rules/{rule['id']}", headers=other)
    ).status_code == 404
    # Чужую услугу нельзя вписать в своё правило
    foreign = await client.post(
        "/api/trainer/schedule/rules",
        headers=other,
        json={"weekday": 0, "start": "10:00", "end": "12:00", "service_ids": [service_id]},
    )
    assert foreign.status_code == 422


async def test_schedule_requires_trainer(client: AsyncClient) -> None:
    headers = await auth(client, 7)
    assert (await client.get("/api/trainer/services", headers=headers)).status_code == 403
    assert (await client.get("/api/trainer/slots", headers=headers)).status_code == 403
