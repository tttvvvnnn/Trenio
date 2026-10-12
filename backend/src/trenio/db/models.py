"""Модели таблиц. Добавляются по этапам вместе с миграциями."""

from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Table,
    Time,
    text,
)
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


class Service(TimestampMixin, Base):
    """Услуга тренера: «Персональная, 60 мин, 1 человек»."""

    __tablename__ = "services"
    __table_args__ = (
        CheckConstraint("duration_min BETWEEN 5 AND 600", name="duration"),
        CheckConstraint("capacity >= 1", name="capacity"),
        CheckConstraint("price IS NULL OR price >= 0", name="price"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trainer_id: Mapped[int] = mapped_column(
        ForeignKey("trainers.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    duration_min: Mapped[int] = mapped_column(Integer)
    # Сколько клиентов одновременно: 1 — индивидуальная, больше — сплит или группа
    capacity: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    # Цена разового занятия в рублях, только для учёта
    price: Mapped[int | None] = mapped_column(Integer)
    # Место; если пусто, берётся адрес тренера
    address: Mapped[str | None] = mapped_column(String(256))
    # Услуги не удаляем, а выключаем: на них будут ссылаться записи и блоки
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


schedule_rule_services = Table(
    "schedule_rule_services",
    Base.metadata,
    Column(
        "rule_id",
        ForeignKey("schedule_rules.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "service_id",
        ForeignKey("services.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class ScheduleRule(TimestampMixin, Base):
    """Строка недельного шаблона: по понедельникам 10:00–14:00 такие-то услуги."""

    __tablename__ = "schedule_rules"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday"),
        CheckConstraint("start_time < end_time", name="time_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trainer_id: Mapped[int] = mapped_column(
        ForeignKey("trainers.id", ondelete="CASCADE"), index=True
    )
    # 0 — понедельник, 6 — воскресенье
    weekday: Mapped[int] = mapped_column(SmallInteger)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    # Пустой список — доступны все активные услуги
    services: Mapped[list[Service]] = relationship(
        secondary=schedule_rule_services, lazy="selectin", order_by=Service.id
    )


class ScheduleException(TimestampMixin, Base):
    """Правка конкретного дня: выходной (весь день или часть) или разовое доп. окно."""

    __tablename__ = "schedule_exceptions"
    __table_args__ = (
        CheckConstraint("kind IN ('closed', 'extra')", name="kind"),
        CheckConstraint(
            "(start_time IS NULL AND end_time IS NULL AND kind = 'closed')"
            " OR (start_time IS NOT NULL AND end_time IS NOT NULL AND start_time < end_time)",
            name="time_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trainer_id: Mapped[int] = mapped_column(
        ForeignKey("trainers.id", ondelete="CASCADE"), index=True
    )
    day: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(16))
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
