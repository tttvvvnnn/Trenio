"""Промо от автора: выключено по умолчанию, карточка после задержки и до закрытия, счётчики."""

from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import ADMIN_TELEGRAM_ID
from tests.factories import make_init_data
from tests.test_api import login
from trenio.db.models import User

SETTINGS: dict[str, Any] = {
    "enabled": True,
    "title": "2 недели TVPN бесплатно",
    "subtitle": "Быстрый интернет",
    "text": "Описание",
    "code": "TRENIO",
    "url": "https://t.me/tvnpgate_bot",
    "button": "Открыть TVPN",
    "delay_days": 3,
}


async def headers_for(client: AsyncClient, user_id: int) -> dict[str, str]:
    token = await login(client, make_init_data(user_id=user_id, first_name="Оля"))
    return {"Authorization": f"Bearer {token}"}


async def test_promo_card_flow(client: AsyncClient, session: AsyncSession) -> None:
    admin = await headers_for(client, ADMIN_TELEGRAM_ID)
    user = await headers_for(client, 4201)

    # По умолчанию выключено
    response = await client.get("/api/me/promo", headers=user)
    assert response.status_code == 200
    assert response.json() is None

    response = await client.put("/api/admin/promo", headers=user, json=SETTINGS)
    assert response.status_code == 403
    response = await client.put(
        "/api/admin/promo", headers=admin, json={**SETTINGS, "url": "javascript:alert(1)"}
    )
    assert response.status_code == 422
    response = await client.put("/api/admin/promo", headers=admin, json=SETTINGS)
    assert response.status_code == 200, response.text
    assert response.json()["settings"] == SETTINGS

    # Новичку строка в Профиле есть, а карточки на главном ещё нет
    promo = (await client.get("/api/me/promo", headers=user)).json()
    assert promo["code"] == "TRENIO"
    assert promo["card"] is False

    await session.execute(
        update(User)
        .where(User.telegram_id == 4201)
        .values(created_at=datetime.now(UTC) - timedelta(days=4))
    )
    await session.commit()
    assert (await client.get("/api/me/promo", headers=user)).json()["card"] is True

    for event in ("shown", "shown", "dismissed"):
        response = await client.post(f"/api/me/promo/{event}", headers=user)
        assert response.status_code == 204, response.text
    assert (await client.post("/api/me/promo/clicked", headers=user)).status_code == 422

    # Закрыл — карточки больше нет, строка в Профиле осталась
    promo = (await client.get("/api/me/promo", headers=user)).json()
    assert promo is not None
    assert promo["card"] is False

    response = await client.post("/api/me/promo/opened", headers=user)
    assert response.status_code == 204
    stats = (await client.get("/api/admin/promo", headers=admin)).json()["stats"]
    assert stats == {"shown": 1, "dismissed": 1, "claimed": 0, "opened": 1}
