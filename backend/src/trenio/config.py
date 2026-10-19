"""Настройки приложения из переменных окружения.

Всё, что отличает dev от prod (база, токен бота, домены), приходит сюда
из окружения. В коде нет предположений о том, где живёт PostgreSQL.
"""

from enum import StrEnum
from functools import lru_cache
from typing import Annotated

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class BotMode(StrEnum):
    # webhook: Telegram сам присылает обновления на наш HTTPS-адрес (dev и prod на сервере).
    # polling: бот сам опрашивает Telegram; удобно, пока нет домена и HTTPS.
    WEBHOOK = "webhook"
    POLLING = "polling"


_DEV_JWT_SECRET = "dev-only-secret-change-me-32-bytes"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    env: str = "local"
    database_url: str = "postgresql+asyncpg://trenio:change-me@localhost:5432/trenio"

    bot_token: SecretStr = SecretStr("")
    bot_mode: BotMode = BotMode.POLLING
    # Публичный адрес, на который Telegram шлёт webhook, например https://dev.example.ru
    webhook_base_url: str = ""
    webhook_secret: SecretStr = SecretStr("")
    # Адрес Mini App, который бот открывает кнопкой
    webapp_url: str = ""

    jwt_secret: SecretStr = SecretStr(_DEV_JWT_SECRET)
    jwt_ttl_minutes: int = 60 * 24 * 7
    # Сколько секунд initData считается свежей
    init_data_max_age: int = 60 * 60 * 24

    # Telegram ID админов: выдают тренерам доступ командами в боте и сами являются тренерами.
    # BETA_TRAINER_IDS — старое имя переменной с этапов 2–3, читается, пока его не переименуют
    admin_telegram_ids: Annotated[frozenset[int], NoDecode] = Field(
        default_factory=frozenset,
        validation_alias=AliasChoices("ADMIN_TELEGRAM_IDS", "BETA_TRAINER_IDS"),
    )
    # Сколько дней действует одноразовая ссылка-приглашение для тренера
    trainer_invite_ttl_days: int = 7

    # Кто оператор персональных данных и куда писать запросы о них: попадают в текст политики
    privacy_operator: str = ""
    privacy_contact: str = ""

    # Platega: приём оплаты подписки по СБП. Пустой PLATEGA_MERCHANT_ID — оплата выключена
    platega_merchant_id: str = ""
    platega_api_key: SecretStr = SecretStr("")

    @property
    def payments_enabled(self) -> bool:
        return bool(self.platega_merchant_id and self.platega_api_key.get_secret_value())

    @field_validator("admin_telegram_ids", mode="before")
    @classmethod
    def _parse_ids(cls, value: object) -> object:
        # В .env это строка "123,456"; пустая строка даёт пустой список
        if isinstance(value, str):
            return frozenset(int(part) for part in value.split(",") if part.strip())
        return value

    @model_validator(mode="after")
    def _require_real_secret_on_server(self) -> "Settings":
        # На сервере забытый JWT_SECRET позволил бы подделать вход любому
        if self.env in {"dev", "prod"} and self.jwt_secret.get_secret_value() in {
            "",
            _DEV_JWT_SECRET,
        }:
            raise ValueError("JWT_SECRET must be set on dev and prod")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
