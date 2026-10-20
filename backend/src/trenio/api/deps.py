from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.auth.tokens import TokenError, decode_access_token
from trenio.config import Settings, get_settings
from trenio.db.models import Trainer, User
from trenio.db.session import get_session
from trenio.services.trainers import get_active_trainer
from trenio.services.users import get_user

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

bearer = HTTPBearer(auto_error=False)


async def current_user(
    session: SessionDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Не авторизован")
    if credentials is None:
        raise unauthorized
    try:
        user_id = decode_access_token(
            credentials.credentials, settings.jwt_secret.get_secret_value()
        )
    except TokenError:
        raise unauthorized from None
    user = await get_user(session, user_id)
    # Удалённый аккаунт: старый токен больше не пускает
    if user is None or user.is_deleted:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def current_trainer(user: CurrentUser, session: SessionDep) -> Trainer:
    trainer = await get_active_trainer(session, user.id)
    if trainer is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа тренера")
    return trainer


CurrentTrainer = Annotated[Trainer, Depends(current_trainer)]
