"""Персональные данные: политика и соглашение, согласие, телефон клиента, удаление аккаунта."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from trenio.api.deps import CurrentTrainer, CurrentUser, SessionDep, SettingsDep
from trenio.services import legal, privacy
from trenio.services.legal import Document
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
    title: str
    text: str
    # Публичная страница документа на сайте
    url: str


def _document(settings: SettingsDep, doc: Document) -> PolicyOut:
    return PolicyOut(
        version=privacy.POLICY_VERSION,
        title=legal.TITLES[doc],
        text=legal.text(settings, doc),
        url=legal.page_url(settings, doc),
    )


@router.get("/legal/{doc}")
async def get_document(doc: Document, settings: SettingsDep) -> PolicyOut:
    """Политика и соглашение открыты всем: их можно прочитать и до входа."""
    return _document(settings, doc)


@router.get("/privacy")
async def get_policy(settings: SettingsDep) -> PolicyOut:
    """Старый адрес политики: им пользуются Mini App прошлых версий."""
    return _document(settings, Document.PRIVACY)


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
