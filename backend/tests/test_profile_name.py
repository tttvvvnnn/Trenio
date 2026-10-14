"""Своё имя клиента: его видит тренер, Telegram его не перезаписывает."""

from httpx import AsyncClient

from tests.factories import make_init_data
from tests.test_api import login


async def test_custom_name_survives_login(client: AsyncClient) -> None:
    token = await login(client, make_init_data(user_id=4001, first_name="Иван"))
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.put(
        "/api/me/name", headers=headers, json={"first_name": " Ваня ", "last_name": " Петров "}
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"first_name": "Ваня", "last_name": "Петров", "name_custom": True}

    # Новый вход с другим именем в Telegram своё имя не трогает
    await login(client, make_init_data(user_id=4001, first_name="Иван Иваныч"))
    me = (await client.get("/api/me", headers=headers)).json()
    assert (me["first_name"], me["last_name"], me["name_custom"]) == ("Ваня", "Петров", True)

    # Сброс возвращает последнее имя из Telegram
    response = await client.delete("/api/me/name", headers=headers)
    assert response.json() == {"first_name": "Иван Иваныч", "last_name": None, "name_custom": False}
    await login(client, make_init_data(user_id=4001, first_name="Иван"))
    me = (await client.get("/api/me", headers=headers)).json()
    assert me["first_name"] == "Иван"

    response = await client.put("/api/me/name", headers=headers, json={"first_name": "  "})
    assert response.status_code == 422
