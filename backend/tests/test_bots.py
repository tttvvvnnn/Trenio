"""Основной бот: строка в bots, к которой привязано всё, что создаётся сейчас."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_trainers import ADMIN_ID, make_invite, make_user
from trenio.db.models import MAIN_BOT_ID, Bot
from trenio.services.bots import sync_main_bot
from trenio.services.trainers import accept_invite, ensure_admin_is_trainer


async def test_main_bot_exists(session: AsyncSession) -> None:
    bots = (await session.scalars(select(Bot))).all()
    assert [(bot.id, bot.slug, bot.is_main) for bot in bots] == [(MAIN_BOT_ID, "main", True)]


async def test_new_trainers_and_invites_belong_to_main_bot(session: AsyncSession) -> None:
    admin = await make_user(session, ADMIN_ID, "Тихон")
    trainer = await ensure_admin_is_trainer(session, admin, {ADMIN_ID})
    assert trainer is not None and trainer.bot_id == MAIN_BOT_ID

    invite = await make_invite(session, timedelta(days=1))
    assert invite.bot_id == MAIN_BOT_ID
    anna = await make_user(session, 7, "Анна")
    assert (await accept_invite(session, anna, invite.code)).bot_id == MAIN_BOT_ID


async def test_sync_main_bot(session: AsyncSession) -> None:
    await sync_main_bot(session, 123456, "TrenioRuBot")
    bot = await session.get(Bot, MAIN_BOT_ID, populate_existing=True)
    assert bot is not None
    assert (bot.external_id, bot.username) == (123456, "TrenioRuBot")
    await sync_main_bot(session, 654321, None)
    bot = await session.get(Bot, MAIN_BOT_ID, populate_existing=True)
    assert bot is not None and (bot.external_id, bot.username) == (654321, None)
