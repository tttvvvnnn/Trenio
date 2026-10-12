from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.auth.telegram import TelegramUser
from trenio.bot.admin import format_trainers
from trenio.bot.handlers import start_text
from trenio.db.models import TrainerInvite, User
from trenio.services.trainers import (
    InviteError,
    InviteRejected,
    accept_invite,
    create_invite,
    ensure_admin_is_trainer,
    get_active_trainer,
    list_trainers,
    set_trainer_active,
)
from trenio.services.users import upsert_telegram_user

ADMIN_ID = 1001
WEEK = timedelta(days=7)


async def make_user(session: AsyncSession, telegram_id: int, first_name: str = "Иван") -> User:
    return await upsert_telegram_user(
        session, TelegramUser(id=telegram_id, first_name=first_name, username=f"user{telegram_id}")
    )


async def make_invite(session: AsyncSession, ttl: timedelta = WEEK) -> TrainerInvite:
    admin = await make_user(session, ADMIN_ID, "Тихон")
    return await create_invite(session, admin, ttl)


async def test_admin_is_trainer_without_invite(session: AsyncSession) -> None:
    admin = await make_user(session, ADMIN_ID, "Тихон")
    trainer = await ensure_admin_is_trainer(session, admin, {ADMIN_ID})
    assert trainer is not None
    assert trainer.display_name == "Тихон"
    # Повторный вход не создаёт второй профиль
    again = await ensure_admin_is_trainer(session, admin, {ADMIN_ID})
    assert again is not None and again.id == trainer.id


async def test_regular_user_is_not_trainer(session: AsyncSession) -> None:
    user = await make_user(session, 7)
    assert await ensure_admin_is_trainer(session, user, {ADMIN_ID}) is None


async def test_invite_grants_trainer_access_once(session: AsyncSession) -> None:
    invite = await make_invite(session)
    anna = await make_user(session, 7, "Анна")
    trainer = await accept_invite(session, anna, invite.code)
    assert trainer.user_id == anna.id
    assert trainer.is_active
    assert trainer.onboarded_at is None

    # Повторное открытие своей ссылки не ошибка
    same = await accept_invite(session, anna, invite.code)
    assert same.id == trainer.id

    boris = await make_user(session, 8, "Борис")
    with pytest.raises(InviteRejected) as rejected:
        await accept_invite(session, boris, invite.code)
    assert rejected.value.reason is InviteError.USED
    assert await get_active_trainer(session, boris.id) is None


async def test_expired_and_unknown_invites_are_rejected(session: AsyncSession) -> None:
    invite = await make_invite(session, ttl=-timedelta(minutes=1))
    user = await make_user(session, 7)
    with pytest.raises(InviteRejected) as expired:
        await accept_invite(session, user, invite.code)
    assert expired.value.reason is InviteError.EXPIRED

    with pytest.raises(InviteRejected) as unknown:
        await accept_invite(session, user, "nonexistent")
    assert unknown.value.reason is InviteError.NOT_FOUND
    assert await get_active_trainer(session, user.id) is None


async def test_existing_trainer_does_not_spend_invite(session: AsyncSession) -> None:
    first, second = await make_invite(session), await make_invite(session)
    anna = await make_user(session, 7, "Анна")
    await accept_invite(session, anna, first.code)
    await accept_invite(session, anna, second.code)

    # Вторая ссылка осталась свободной и годится другому человеку
    boris = await make_user(session, 8, "Борис")
    trainer = await accept_invite(session, boris, second.code)
    assert trainer.user_id == boris.id


async def test_revoke_and_restore_keep_profile(session: AsyncSession) -> None:
    invite = await make_invite(session)
    anna = await make_user(session, 7, "Анна")
    trainer = await accept_invite(session, anna, invite.code)

    await set_trainer_active(session, trainer.id, False)
    assert await get_active_trainer(session, anna.id) is None

    # Новая ссылка возвращает доступ тому же профилю, с той же ссылкой для клиентов
    restored = await accept_invite(session, anna, (await make_invite(session)).code)
    assert restored.id == trainer.id
    assert restored.is_active
    assert restored.invite_code == trainer.invite_code


async def test_trainers_list_text(session: AsyncSession) -> None:
    assert "Тренеров пока нет" in format_trainers([])

    admin = await make_user(session, ADMIN_ID, "Тихон")
    await ensure_admin_is_trainer(session, admin, {ADMIN_ID})
    anna = await make_user(session, 7, "Анна")
    trainer = await accept_invite(session, anna, (await make_invite(session)).code)
    await set_trainer_active(session, trainer.id, False)

    text = format_trainers(await list_trainers(session))
    assert "1. Тихон @user1001 — активен, профиль не заполнен" in text
    assert "2. Анна @user7 — отключён" in text


async def test_start_text_depends_on_role(session: AsyncSession) -> None:
    assert "ссылку-приглашение" in start_text("Иван", None, admin=False)

    admin = await make_user(session, ADMIN_ID, "Тихон")
    trainer = await ensure_admin_is_trainer(session, admin, {ADMIN_ID})
    assert trainer is not None
    text = start_text("Тихон", trainer, admin=True)
    assert "заполните профиль" in text
    assert "/invite" in text

    trainer.onboarded_at = datetime.now(UTC)
    assert "заполните профиль" not in start_text("Тихон", trainer, admin=False)
