from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from trenio.api.deps import SessionDep, SettingsDep
from trenio.auth.telegram import InitDataError, validate_init_data
from trenio.auth.tokens import create_access_token
from trenio.services.users import upsert_telegram_user

router = APIRouter(prefix="/auth", tags=["auth"])


class TelegramLoginIn(BaseModel):
    init_data: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/telegram")
async def login_telegram(
    body: TelegramLoginIn, session: SessionDep, settings: SettingsDep
) -> TokenOut:
    """Обменивает подписанную Telegram initData на наш токен доступа."""
    try:
        tg_user = validate_init_data(
            body.init_data,
            settings.bot_token.get_secret_value(),
            max_age=settings.init_data_max_age,
        )
    except InitDataError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверные данные Telegram") from None
    user = await upsert_telegram_user(session, tg_user)
    token = create_access_token(
        user.id, settings.jwt_secret.get_secret_value(), settings.jwt_ttl_minutes
    )
    return TokenOut(access_token=token)
