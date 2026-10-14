"""Картинки фото пользователей. Без входа: тег <img> не умеет передавать токен,
а угадать случайный ключ в адресе нельзя."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Response, status

from trenio.api.deps import SessionDep
from trenio.services import avatars

router = APIRouter(tags=["avatars"])


@router.get("/avatars/{key}")
async def get_avatar(
    key: Annotated[str, Path(max_length=32, pattern=r"^[A-Za-z0-9_-]+$")], session: SessionDep
) -> Response:
    data = await avatars.get_image(session, key)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Фото не найдено")
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={
            # Новое фото получает новый ключ, поэтому старый адрес можно кэшировать навсегда
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )
