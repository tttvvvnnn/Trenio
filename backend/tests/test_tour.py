"""Вводный тур: у тренера и клиента отмечается отдельно."""

from httpx import AsyncClient

from tests.factories import make_init_data
from tests.test_api import login


async def test_tour_is_marked_per_role(client: AsyncClient) -> None:
    token = await login(client, make_init_data(user_id=4101, first_name="Оля"))
    headers = {"Authorization": f"Bearer {token}"}

    me = (await client.get("/api/me", headers=headers)).json()
    assert (me["trainer_tour_done"], me["client_tour_done"]) == (False, False)

    response = await client.post("/api/me/tour/client", headers=headers)
    assert response.status_code == 204, response.text
    # Повторный проход из Профиля тоже ок
    response = await client.post("/api/me/tour/client", headers=headers)
    assert response.status_code == 204

    me = (await client.get("/api/me", headers=headers)).json()
    assert (me["trainer_tour_done"], me["client_tour_done"]) == (False, True)

    response = await client.post("/api/me/tour/trainer", headers=headers)
    assert response.status_code == 204
    me = (await client.get("/api/me", headers=headers)).json()
    assert me["trainer_tour_done"] is True

    response = await client.post("/api/me/tour/admin", headers=headers)
    assert response.status_code == 422
