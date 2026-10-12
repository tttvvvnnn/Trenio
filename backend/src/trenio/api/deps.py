from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.auth.tokens import TokenError, decode_access_token
from trenio.config import Settings, get_settings
from trenio.db.models import User
from trenio.db.session import get_session
from trenio.services.users import get_user

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

_bearer = HTTPBearer(auto_error=False)


async def current_user(
    session: SessionDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
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
    if user is None:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(current_user)]
