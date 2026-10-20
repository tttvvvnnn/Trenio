"""Вход в веб-админку и журнал действий админа.

Вход в два шага. Telegram Login Widget подтверждает, что это аккаунт админа, после чего
появляется сессия в статусе pending и в бот уходит «Вход в админку с …, это вы?». Пускаем
только после кнопки «Да». Украденная кука без телефона админа бесполезна, а о попытке
входа админ узнаёт сразу.
"""

import secrets
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.db.models import AdminAuditEntry, AdminSession, User


class SessionStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    DENIED = "denied"


class SessionState(StrEnum):
    """Что видит страница входа: ждать кнопку в боте, пускать или начинать заново."""

    PENDING = "pending"
    ACTIVE = "active"
    DENIED = "denied"
    EXPIRED = "expired"


def new_token() -> str:
    return secrets.token_urlsafe(32)


async def create_session(
    session: AsyncSession,
    user: User,
    now: datetime,
    ttl: timedelta,
    ip: str | None,
    user_agent: str | None,
) -> AdminSession:
    admin_session = AdminSession(
        id=new_token(),
        user_id=user.id,
        csrf_token=new_token(),
        ip=ip,
        user_agent=(user_agent or "")[:256] or None,
        created_at=now,
        expires_at=now + ttl,
    )
    session.add(admin_session)
    await session.flush()
    return admin_session


def state(admin_session: AdminSession, now: datetime, confirm_within: timedelta) -> SessionState:
    if admin_session.status == SessionStatus.DENIED:
        return SessionState.DENIED
    if admin_session.revoked_at is not None or admin_session.expires_at <= now:
        return SessionState.EXPIRED
    if admin_session.status == SessionStatus.PENDING:
        if now - admin_session.created_at > confirm_within:
            return SessionState.EXPIRED
        return SessionState.PENDING
    return SessionState.ACTIVE


async def get_session(session: AsyncSession, session_id: str) -> AdminSession | None:
    return await session.get(AdminSession, session_id)


async def answer_confirmation(
    session: AsyncSession,
    session_id: str,
    user: User,
    approve: bool,
    now: datetime,
    confirm_within: timedelta,
) -> AdminSession | None:
    """Ответ на кнопку в боте. None — сессии нет, она чужая или уже не ждёт ответа."""
    admin_session = await get_session(session, session_id)
    if (
        admin_session is None
        or admin_session.user_id != user.id
        or state(admin_session, now, confirm_within) is not SessionState.PENDING
    ):
        return None
    if approve:
        admin_session.status = SessionStatus.ACTIVE
        admin_session.confirmed_at = now
    else:
        admin_session.status = SessionStatus.DENIED
        admin_session.revoked_at = now
    await audit(
        session,
        user.id,
        "login.confirmed" if approve else "login.denied",
        session_id=admin_session.id,
        ip=admin_session.ip,
    )
    return admin_session


async def list_sessions(session: AsyncSession, user: User, now: datetime) -> list[AdminSession]:
    """Действующие входы админа, свежие сверху."""
    rows = await session.scalars(
        select(AdminSession)
        .where(
            AdminSession.user_id == user.id,
            AdminSession.status == SessionStatus.ACTIVE,
            AdminSession.revoked_at.is_(None),
            AdminSession.expires_at > now,
        )
        .order_by(AdminSession.created_at.desc())
    )
    return list(rows)


async def revoke(session: AsyncSession, admin_session: AdminSession, now: datetime) -> None:
    if admin_session.revoked_at is None:
        admin_session.revoked_at = now


async def audit(
    session: AsyncSession,
    user_id: int | None,
    action: str,
    *,
    session_id: str | None = None,
    target: str | None = None,
    payload: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    """Строка в журнал. Коммит за вызывающим: запись попадает в базу вместе с действием."""
    session.add(
        AdminAuditEntry(
            user_id=user_id,
            session_id=session_id,
            action=action,
            target=target,
            payload=payload or {},
            ip=ip,
        )
    )


def confirmation_text(admin_session: AdminSession, when: str) -> str:
    where = admin_session.ip or "неизвестного адреса"
    device = admin_session.user_agent or "неизвестное устройство"
    return (
        f"Вход в веб-админку Trenio\n\n{when} МСК, с адреса {where}\n{device}\n\n"
        "Это вы? Если нет, нажмите «Нет»: вход будет отклонён."
    )


@dataclass
class LoginLimiter:
    """Не больше attempts попыток входа с одного адреса за window. Учёт в памяти процесса."""

    attempts: int = 10
    window: timedelta = timedelta(minutes=10)
    seen: dict[str, deque[datetime]] = field(default_factory=dict)

    def allow(self, key: str, now: datetime) -> bool:
        hits = self.seen.setdefault(key, deque())
        while hits and now - hits[0] >= self.window:
            hits.popleft()
        if len(hits) >= self.attempts:
            return False
        hits.append(now)
        # Адреса без свежих попыток больше не нужны
        for old in [k for k, v in self.seen.items() if not v]:
            del self.seen[old]
        return True
