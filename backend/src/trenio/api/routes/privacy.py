"""Персональные данные: политика, согласие, телефон клиента, удаление аккаунта."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from trenio.api.deps import CurrentTrainer, CurrentUser, SessionDep, SettingsDep
from trenio.services import privacy
from trenio.services.privacy import PhoneError, PhoneRejected

router = APIRouter(tags=["privacy"])

_PHONE_ERRORS = {
    PhoneError.INVALID: (422, "Не похоже на номер телефона"),
    PhoneError.NO_CONSENT: (422, "Отметьте, что клиент согласен хранить его телефон"),
    PhoneError.NOT_FOUND: (404, "Клиент не найден"),
}


def phone_error(rejected: PhoneRejected) -> HTTPException:
    code, message = _PHONE_ERRORS[rejected.reason]
    return HTTPException(code, message)


class PolicyOut(BaseModel):
    version: int
    text: str


@router.get("/privacy")
async def get_policy(settings: SettingsDep) -> PolicyOut:
    """Текст политики открыт всем: его можно прочитать и до входа."""
    return PolicyOut(
        version=privacy.POLICY_VERSION,
        text=privacy.policy_text(settings.privacy_operator, settings.privacy_contact),
    )


@router.post("/me/consent", status_code=status.HTTP_204_NO_CONTENT)
async def give_consent(user: CurrentUser, session: SessionDep) -> None:
    await privacy.give_consent(session, user, datetime.now(UTC))


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(user: CurrentUser, session: SessionDep) -> None:
    """Удалить аккаунт. Записи и оплаты у тренеров остаются обезличенными."""
    await privacy.delete_account(session, user, datetime.now(UTC))


class PhoneIn(BaseModel):
    # null — удалить телефон
    phone: Annotated[str | None, Field(max_length=32)]
    # Тренер подтверждает, что клиент согласен хранить телефон
    consent: bool = False


class PhoneOut(BaseModel):
    phone: str | None


@router.put("/trainer/clients/{client_id}/phone")
async def set_client_phone(
    client_id: int, body: PhoneIn, trainer: CurrentTrainer, session: SessionDep
) -> PhoneOut:
    phone = (body.phone or "").strip() or None
    try:
        link = await privacy.set_client_phone(
            session, trainer, client_id, phone, body.consent, datetime.now(UTC)
        )
    except PhoneRejected as rejected:
        raise phone_error(rejected) from None
    return PhoneOut(phone=link.phone)


@router.delete("/client/trainers/{trainer_id}/phone", status_code=status.HTTP_204_NO_CONTENT)
async def remove_my_phone(trainer_id: int, user: CurrentUser, session: SessionDep) -> None:
    """Клиент удаляет свой телефон у тренера."""
    try:
        await privacy.remove_my_phone(session, user, trainer_id)
    except PhoneRejected as rejected:
        raise phone_error(rejected) from None
