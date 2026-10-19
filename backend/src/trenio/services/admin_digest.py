"""Сводка для админа в Telegram: по понедельникам утром и по команде /digest.

Те же цифры, что на главном экране админки: рост за неделю и кому из тренеров написать.
"""

from collections.abc import Collection
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.db.models import ClientError
from trenio.services.admin_insights import Attention, Reason, attention, pulse


def plural(count: int, one: str, few: str, many: str) -> str:
    """1 день, 2 дня, 5 дней."""
    if count % 10 == 1 and count % 100 != 11:
        word = one
    elif 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        word = few
    else:
        word = many
    return f"{count} {word}"


def _delta(current: int, previous: int, unit: str = "") -> str:
    diff = current - previous
    if diff == 0:
        return "как неделей раньше"
    return f"{'+' if diff > 0 else '−'}{abs(diff)}{unit} к прошлой неделе"


def reason_text(item: Attention) -> str:
    days = plural(item.count, "день", "дня", "дней")
    match item.reason:
        case Reason.NOT_SET_UP:
            return f"не настроил услуги и часы, {days}"
        case Reason.NO_CLIENTS:
            return f"нет клиентов, {days}"
        case Reason.QUIET:
            return f"затих, {days} без занятий"
        case Reason.UNMARKED:
            return f"{plural(item.count, 'занятие', 'занятия', 'занятий')} без отметки"


async def digest_text(
    session: AsyncSession, now: datetime, admin_telegram_ids: Collection[int]
) -> str:
    data = await pulse(session, now)
    live, live_prev = data.live_trainers[-1], data.live_trainers[-2]
    sessions, sessions_prev = data.sessions[-1], data.sessions[-2]
    share, share_prev = data.self_booked[-1], data.self_booked[-2]
    lines = [
        "Trenio за неделю",
        "",
        f"Живые тренеры: {live} ({_delta(live, live_prev)})",
        f"Занятий: {sessions} ({_delta(sessions, sessions_prev)})",
    ]
    if share is not None:
        change = f" ({_delta(share, share_prev, ' п.п.')})" if share_prev is not None else ""
        lines.append(f"Записались сами: {share}%{change}")

    items = await attention(session, now, admin_telegram_ids)
    lines.append("")
    if items:
        lines.append("Требуют внимания:")
        for item in items:
            username = item.trainer.user.username
            contact = f" @{username}" if username else ""
            lines.append(f"• {item.trainer.display_name}{contact}: {reason_text(item)}")
    else:
        lines.append("Все тренеры настроились, работают и отмечают занятия.")

    errors = int(
        await session.scalar(
            select(func.count(ClientError.id)).where(
                ClientError.created_at >= now - timedelta(days=7)
            )
        )
        or 0
    )
    if errors:
        lines.append("")
        lines.append(f"Ошибок в приложении за неделю: {errors}.")
    return "\n".join(lines)
