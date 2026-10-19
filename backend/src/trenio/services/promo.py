"""Промо-предложение от автора Trenio: карточка на главном экране и строка в Профиле.

Тексты, промокод и ссылку админ меняет в админ-панели, без деплоя. По умолчанию выключено.
"""

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.db.models import AppSetting, PromoView, User

SETTINGS_KEY = "promo"

PromoEvent = Literal["shown", "dismissed", "claimed", "opened"]


@dataclass(frozen=True)
class PromoSettings:
    enabled: bool
    # Заголовок карточки, строки в Профиле и экрана с кодом
    title: str
    # Одна строка под заголовком карточки
    subtitle: str
    # Описание на экране с кодом
    text: str
    code: str
    # Куда ведёт кнопка: бот в Telegram или сайт
    url: str
    button: str
    # Через сколько дней после первого входа показать карточку на главном экране
    delay_days: int


DEFAULT = PromoSettings(
    enabled=False,
    title="2 недели TVPN бесплатно",
    subtitle="Быстрый и стабильный интернет на телефоне и ноутбуке",
    text=(
        "TVPN — сервис автора Trenio для быстрого и стабильного интернета. "
        "Пользователям Trenio первые две недели бесплатно."
    ),
    code="TRENIO",
    url="https://t.me/tvnpgate_bot",
    button="Открыть TVPN",
    delay_days=3,
)


@dataclass(frozen=True)
class PromoStats:
    # Сколько людей увидели карточку, закрыли её, открыли код и перешли по кнопке
    shown: int
    dismissed: int
    claimed: int
    opened: int


async def get_settings(session: AsyncSession) -> PromoSettings:
    row = await session.get(AppSetting, SETTINGS_KEY)
    if row is None:
        return DEFAULT
    # Поля, которых ещё не было при сохранении, берём по умолчанию
    known = {key: value for key, value in row.value.items() if key in asdict(DEFAULT)}
    return replace(DEFAULT, **known)


async def save_settings(session: AsyncSession, settings: PromoSettings) -> None:
    row = await session.get(AppSetting, SETTINGS_KEY)
    if row is None:
        session.add(AppSetting(key=SETTINGS_KEY, value=asdict(settings)))
    else:
        row.value = asdict(settings)
    await session.commit()


def card_due(settings: PromoSettings, user: User, view: PromoView | None, now: datetime) -> bool:
    """Карточка на главном экране: пока человек её не закрыл и не открыл код,
    и не раньше чем через delay_days после первого входа, чтобы не мешать знакомству."""
    if not settings.enabled:
        return False
    if view is not None and (view.dismissed_at is not None or view.claimed_at is not None):
        return False
    return now - user.created_at >= timedelta(days=settings.delay_days)


async def get_view(session: AsyncSession, user_id: int) -> PromoView | None:
    return await session.get(PromoView, user_id)


async def record(session: AsyncSession, user: User, event: PromoEvent, now: datetime) -> None:
    """Запоминает первое такое действие; повторное время не меняет."""
    view = await session.get(PromoView, user.id)
    if view is None:
        view = PromoView(user_id=user.id)
        session.add(view)
    column = f"{event}_at"
    if getattr(view, column) is None:
        setattr(view, column, now)
    await session.commit()


async def stats(session: AsyncSession) -> PromoStats:
    row = (
        await session.execute(
            select(
                func.count(PromoView.shown_at),
                func.count(PromoView.dismissed_at),
                func.count(PromoView.claimed_at),
                func.count(PromoView.opened_at),
            )
        )
    ).one()
    return PromoStats(shown=row[0], dismissed=row[1], claimed=row[2], opened=row[3])
