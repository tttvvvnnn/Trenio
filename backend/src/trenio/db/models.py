"""Модели таблиц. Добавляются по этапам вместе с миграциями."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from trenio.db.base import Base, TimestampMixin

DEFAULT_TIMEZONE = "Europe/Moscow"


class User(TimestampMixin, Base):
    __tablename__ = "users"

    # Внутренний id; telegram_id лишь один из способов входа (потом появятся телефон и т.п.)
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    first_name: Mapped[str] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    username: Mapped[str | None] = mapped_column(String(64))
    language_code: Mapped[str | None] = mapped_column(String(16))


class Trainer(TimestampMixin, Base):
    """Профиль тренера. Есть строка и is_active — значит, у пользователя есть бета-доступ."""

    __tablename__ = "trainers"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    # Как тренера видят клиенты; по умолчанию имя из Telegram
    display_name: Mapped[str] = mapped_column(String(128))
    timezone: Mapped[str] = mapped_column(
        String(64), default=DEFAULT_TIMEZONE, server_default=DEFAULT_TIMEZONE
    )
    # Адрес зала по умолчанию для услуг
    address: Mapped[str | None] = mapped_column(String(256))
    # Код персональной ссылки для клиентов (t.me/бот?start=c_<код>), понадобится на этапе 5
    invite_code: Mapped[str] = mapped_column(String(32), unique=True)
    # Записи подтверждаются сразу или после одобрения тренера
    auto_confirm: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    # За сколько часов до начала клиент ещё может отменить запись сам
    cancel_hours: Mapped[int] = mapped_column(Integer, default=12, server_default=text("12"))
    # Админ может отключить тренера; данные при этом сохраняются
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    # Когда тренер прошёл первую настройку в Mini App; None — ещё не прошёл
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(lazy="joined")


class TrainerInvite(TimestampMixin, Base):
    """Одноразовая ссылка, по которой админ выдаёт человеку доступ тренера."""

    __tablename__ = "trainer_invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
