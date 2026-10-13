"""Клиенты тренера: привязка по персональной ссылке и списки с обеих сторон."""

from collections.abc import Sequence
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.db.models import Trainer, TrainerClient, User

# Префикс параметра /start в ссылке тренера для клиентов: t.me/бот?start=c_<код>
CLIENT_INVITE_PREFIX = "c_"


class LinkError(StrEnum):
    NOT_FOUND = "not_found"
    OWN_LINK = "own_link"


class LinkRejected(Exception):
    def __init__(self, reason: LinkError) -> None:
        super().__init__(reason)
        self.reason = reason


def client_invite_link(bot_username: str, trainer: Trainer) -> str:
    return f"https://t.me/{bot_username}?start={CLIENT_INVITE_PREFIX}{trainer.invite_code}"


async def link_client(session: AsyncSession, user: User, invite_code: str) -> Trainer:
    """Делает пользователя клиентом тренера. Повторный переход по ссылке ничего не ломает."""
    trainer = await session.scalar(
        select(Trainer).where(Trainer.invite_code == invite_code, Trainer.is_active.is_(True))
    )
    if trainer is None:
        raise LinkRejected(LinkError.NOT_FOUND)
    if trainer.user_id == user.id:
        raise LinkRejected(LinkError.OWN_LINK)
    await session.execute(
        insert(TrainerClient)
        .values(trainer_id=trainer.id, user_id=user.id)
        .on_conflict_do_nothing(constraint="uq_trainer_clients_pair")
    )
    await session.commit()
    return trainer


async def list_clients(session: AsyncSession, trainer: Trainer) -> Sequence[TrainerClient]:
    stmt = (
        select(TrainerClient)
        .join(TrainerClient.user)
        .where(TrainerClient.trainer_id == trainer.id)
        .order_by(User.first_name, User.last_name, TrainerClient.id)
    )
    return (await session.scalars(stmt)).all()


async def is_client(session: AsyncSession, trainer: Trainer, user_id: int) -> bool:
    found = await session.scalar(
        select(TrainerClient.id).where(
            TrainerClient.trainer_id == trainer.id, TrainerClient.user_id == user_id
        )
    )
    return found is not None


async def list_my_trainers(session: AsyncSession, user: User) -> Sequence[Trainer]:
    """Тренеры, к которым пользователь может записаться. Отключённых не показываем."""
    stmt = (
        select(Trainer)
        .join(TrainerClient, TrainerClient.trainer_id == Trainer.id)
        .where(TrainerClient.user_id == user.id, Trainer.is_active.is_(True))
        .order_by(Trainer.display_name, Trainer.id)
    )
    return (await session.scalars(stmt)).all()


async def get_my_trainer(session: AsyncSession, user: User, trainer_id: int) -> Trainer | None:
    stmt = (
        select(Trainer)
        .join(TrainerClient, TrainerClient.trainer_id == Trainer.id)
        .where(
            Trainer.id == trainer_id,
            TrainerClient.user_id == user.id,
            Trainer.is_active.is_(True),
        )
    )
    return await session.scalar(stmt)
