from httpx import AsyncClient

from tests.conftest import ADMIN_TELEGRAM_ID
from tests.factories import make_init_data


async def login(client: AsyncClient, init_data: str) -> str:
    response = await client.post("/api/auth/telegram", json={"init_data": init_data})
    assert response.status_code == 200, response.text
    token: str = response.json()["access_token"]
    return token


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["env"] == "test"


async def test_login_and_me(client: AsyncClient) -> None:
    token = await login(client, make_init_data(user_id=7, first_name="Анна"))
    response = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    me = response.json()
    assert me["first_name"] == "Анна"
    assert me["is_trainer"] is False


async def test_repeated_login_keeps_same_user(client: AsyncClient) -> None:
    first = await login(client, make_init_data(user_id=7, first_name="Анна"))
    second = await login(client, make_init_data(user_id=7, first_name="Аня"))
    headers_first = {"Authorization": f"Bearer {first}"}
    headers_second = {"Authorization": f"Bearer {second}"}
    me_first = (await client.get("/api/me", headers=headers_first)).json()
    me_second = (await client.get("/api/me", headers=headers_second)).json()
    assert me_first["id"] == me_second["id"]
    assert me_second["first_name"] == "Аня"


async def test_regular_user_is_not_trainer(client: AsyncClient) -> None:
    token = await login(client, make_init_data(user_id=7))
    headers = {"Authorization": f"Bearer {token}"}
    me = (await client.get("/api/me", headers=headers)).json()
    assert me["is_trainer"] is False
    assert me["is_admin"] is False
    assert me["trainer"] is None
    assert (await client.get("/api/trainer/me", headers=headers)).status_code == 403


async def test_admin_becomes_trainer_on_login(client: AsyncClient) -> None:
    token = await login(client, make_init_data(user_id=ADMIN_TELEGRAM_ID, first_name="Тихон"))
    me = (await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})).json()
    assert me["is_trainer"] is True
    assert me["is_admin"] is True
    assert me["trainer"]["display_name"] == "Тихон"
    assert me["trainer"]["timezone"] == "Europe/Moscow"
    # Профиль ещё не заполнен: Mini App покажет онбординг
    assert me["trainer"]["onboarded_at"] is None


async def test_trainer_onboarding(client: AsyncClient) -> None:
    token = await login(client, make_init_data(user_id=ADMIN_TELEGRAM_ID))
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.patch(
        "/api/trainer/me",
        headers=headers,
        json={
            "display_name": "  Тихон Тренер ",
            "timezone": "Asia/Yekaterinburg",
            "address": "Зал на Ленина, 1",
        },
    )
    assert response.status_code == 200, response.text
    profile = response.json()
    assert profile["display_name"] == "Тихон Тренер"
    assert profile["timezone"] == "Asia/Yekaterinburg"
    assert profile["onboarded_at"] is not None

    # Частичное изменение не трогает остальные поля и дату онбординга
    response = await client.patch(
        "/api/trainer/me", headers=headers, json={"cancel_hours": 24, "auto_confirm": False}
    )
    updated = response.json()
    assert updated["cancel_hours"] == 24
    assert updated["auto_confirm"] is False
    assert updated["address"] == "Зал на Ленина, 1"
    assert updated["onboarded_at"] == profile["onboarded_at"]


async def test_trainer_rejects_unknown_timezone(client: AsyncClient) -> None:
    token = await login(client, make_init_data(user_id=ADMIN_TELEGRAM_ID))
    headers = {"Authorization": f"Bearer {token}"}
    for timezone in ("Mars/Olympus", "UTC", "../etc/passwd"):
        response = await client.patch(
            "/api/trainer/me", headers=headers, json={"timezone": timezone}
        )
        assert response.status_code == 422, timezone


async def test_forged_init_data_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/telegram", json={"init_data": make_init_data(bot_token="999:OTHER")}
    )
    assert response.status_code == 401


async def test_me_requires_token(client: AsyncClient) -> None:
    assert (await client.get("/api/me")).status_code == 401
    bad = await client.get("/api/me", headers={"Authorization": "Bearer nonsense"})
    assert bad.status_code == 401
