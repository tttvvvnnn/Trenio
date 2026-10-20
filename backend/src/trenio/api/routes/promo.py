"""Промо-предложение от автора Trenio: что видит пользователь и настройки в админ-панели."""

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from trenio.api.deps import CurrentUser, SessionDep
from trenio.api.routes.admin import CurrentAdmin
from trenio.services import promo

router = APIRouter(tags=["promo"])


class PromoOut(BaseModel):
    title: str
    subtitle: str
    text: str
    code: str
    url: str
    button: str
    # Показать карточку на главном экране; строка в Профиле есть всегда, пока промо включено
    card: bool


@router.get("/me/promo")
async def get_promo(user: CurrentUser, session: SessionDep) -> PromoOut | None:
    """Текущее предложение; null — промо выключено."""
    settings = await promo.get_settings(session)
    if not settings.enabled:
        return None
    view = await promo.get_view(session, user.id)
    return PromoOut(
        title=settings.title,
        subtitle=settings.subtitle,
        text=settings.text,
        code=settings.code,
        url=settings.url,
        button=settings.button,
        card=promo.card_due(settings, user, view, datetime.now(UTC)),
    )


@router.post("/me/promo/{event}", status_code=status.HTTP_204_NO_CONTENT)
async def promo_event(event: promo.PromoEvent, user: CurrentUser, session: SessionDep) -> None:
    """Карточку показали, закрыли, открыли код или перешли по кнопке."""
    await promo.record(session, user, event, datetime.now(UTC))


# --- Админ-панель ---


class PromoSettingsIO(BaseModel):
    enabled: bool
    title: Annotated[str, Field(min_length=1, max_length=80)]
    subtitle: Annotated[str, Field(max_length=160)]
    text: Annotated[str, Field(max_length=600)]
    code: Annotated[str, Field(min_length=1, max_length=32)]
    url: Annotated[str, Field(pattern=r"^https://\S+$", max_length=200)]
    button: Annotated[str, Field(min_length=1, max_length=32)]
    delay_days: Annotated[int, Field(ge=0, le=60)]


class PromoStatsOut(BaseModel):
    shown: int
    dismissed: int
    claimed: int
    opened: int


class AdminPromoOut(BaseModel):
    settings: PromoSettingsIO
    stats: PromoStatsOut


async def _admin_promo(session: SessionDep) -> AdminPromoOut:
    settings = await promo.get_settings(session)
    stats = await promo.stats(session)
    return AdminPromoOut(
        settings=PromoSettingsIO(**asdict(settings)), stats=PromoStatsOut(**asdict(stats))
    )


@router.get("/admin/promo")
async def get_admin_promo(_: CurrentAdmin, session: SessionDep) -> AdminPromoOut:
    return await _admin_promo(session)


@router.put("/admin/promo")
async def set_admin_promo(
    body: PromoSettingsIO, admin: CurrentAdmin, session: SessionDep
) -> AdminPromoOut:
    await admin.audit(session, "promo.updated", payload=body.model_dump(mode="json"))
    await promo.save_settings(session, promo.PromoSettings(**body.model_dump()))
    return await _admin_promo(session)
