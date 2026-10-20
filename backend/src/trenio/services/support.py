"""Обращения тренеров: форма «Написать нам» в Профиле Mini App и раздел «Обращения» в админке.

Тренер выбирает тип и пишет текст, у отзыва ещё оценка. Админ отвечает из веб-админки,
ответ уходит тренеру в бот и виден в истории обращений в Mini App.
"""

from collections.abc import Sequence
from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.db.models import SupportTicket, Trainer

# Защита от случайной очереди одинаковых сообщений, а не ограничение для живого человека
DAILY_LIMIT = 10
TRAINER_HISTORY = 20
ADMIN_LIMIT = 200


class Kind(StrEnum):
    QUESTION = "question"
    PROBLEM = "problem"
    IDEA = "idea"
    REVIEW = "review"


class Status(StrEnum):
    NEW = "new"
    ANSWERED = "answered"
    CLOSED = "closed"


KIND_TEXT = {
    Kind.QUESTION: "Вопрос",
    Kind.PROBLEM: "Проблема",
    Kind.IDEA: "Идея",
    Kind.REVIEW: "Отзыв",
}


async def sent_today(session: AsyncSession, trainer_id: int, now: datetime) -> int:
    return (
        await session.scalar(
            select(func.count()).where(
                SupportTicket.trainer_id == trainer_id,
                SupportTicket.created_at > now - timedelta(days=1),
            )
        )
        or 0
    )


async def create(
    session: AsyncSession,
    trainer: Trainer,
    kind: Kind,
    text: str,
    rating: int | None,
    now: datetime,
) -> SupportTicket:
    """Коммит за вызывающим."""
    ticket = SupportTicket(
        trainer_id=trainer.id,
        kind=kind.value,
        text=text,
        rating=rating if kind is Kind.REVIEW else None,
        created_at=now,
    )
    session.add(ticket)
    await session.flush()
    return ticket


async def of_trainer(session: AsyncSession, trainer_id: int) -> Sequence[SupportTicket]:
    return (
        await session.scalars(
            select(SupportTicket)
            .where(SupportTicket.trainer_id == trainer_id)
            .order_by(SupportTicket.created_at.desc(), SupportTicket.id.desc())
            .limit(TRAINER_HISTORY)
        )
    ).all()


async def for_admin(session: AsyncSession, status: Status | None) -> Sequence[SupportTicket]:
    query = select(SupportTicket)
    if status is not None:
        query = query.where(SupportTicket.status == status.value)
    # Новые сверху, внутри — свежие первыми
    query = query.order_by(
        (SupportTicket.status == Status.NEW.value).desc(),
        SupportTicket.created_at.desc(),
        SupportTicket.id.desc(),
    )
    return (await session.scalars(query.limit(ADMIN_LIMIT))).all()


def admin_alert(trainer: Trainer, ticket: SupportTicket) -> str:
    stars = f" {'★' * ticket.rating}" if ticket.rating else ""
    return (
        f"Новое обращение · {KIND_TEXT[Kind(ticket.kind)]}{stars}\n"
        f"{trainer.display_name}\n\n{ticket.text[:1500]}\n\n"
        "Ответить можно в веб-админке, раздел «Обращения»."
    )


def answer_message(ticket: SupportTicket, answer: str) -> str:
    quote = ticket.text if len(ticket.text) <= 300 else ticket.text[:300] + "…"
    return f"Ответ команды Trenio на ваше обращение\n\n«{quote}»\n\n{answer}"
