"""Юридические документы: политика конфиденциальности и пользовательское соглашение.

Тексты лежат в trenio/legal/*.txt, чтобы их было удобно править. Абзацы — одной
строкой: Mini App и браузер сами переносят их по ширине экрана. Оператор, контакт и
адрес сайта приходят из настроек, цены и лимиты — из кода подписки, чтобы текст не
расходился с тем, что видит тренер.
"""

from enum import StrEnum
from functools import cache
from importlib import resources
from urllib.parse import urlsplit

from trenio.config import Settings
from trenio.services import billing, subscription
from trenio.services.privacy import DELETED_NAME

# Дата редакции: меняется вместе с текстом
UPDATED = "19 октября 2026 г."

DEFAULT_SITE = "https://trenio.tvpngate.cc"


class Document(StrEnum):
    PRIVACY = "privacy"
    TERMS = "terms"


TITLES = {
    Document.PRIVACY: "Политика конфиденциальности",
    Document.TERMS: "Пользовательское соглашение",
}


@cache
def _template(doc: Document) -> str:
    return resources.files("trenio.legal").joinpath(f"{doc.value}.txt").read_text("utf-8")


def site_url(settings: Settings) -> str:
    """Адрес сайта без пути: https://trenio.tvpngate.cc."""
    parts = urlsplit(settings.webapp_url)
    if not parts.scheme or not parts.netloc:
        return DEFAULT_SITE
    return f"{parts.scheme}://{parts.netloc}"


def page_url(settings: Settings, doc: Document) -> str:
    """Публичная страница документа: открывается в браузере без входа."""
    return f"{site_url(settings)}/{doc.value}"


def text(settings: Settings, doc: Document) -> str:
    return _template(doc).format(
        date=UPDATED,
        site=site_url(settings),
        operator=settings.privacy_operator.strip() or "владелец сервиса Trenio",
        contact=settings.privacy_contact.strip() or "напишите боту Trenio",
        deleted=DELETED_NAME,
        trial_days=subscription.TRIAL_DAYS,
        free_clients=subscription.FREE_CLIENT_LIMIT,
        price_month=subscription.PLANS["month"].price,
        referral_percent=billing.REFERRAL_PERCENT,
    )
