"""Модели таблиц. Добавляются по этапам вместе с миграциями."""

from datetime import date, datetime, time
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Table,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from trenio.db.base import Base, TimestampMixin

DEFAULT_TIMEZONE = "Europe/Moscow"


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("avatar_mode IN ('telegram', 'custom', 'none')", name="avatar_mode"),
    )

    # Внутренний id; telegram_id лишь один из способов входа (потом появятся телефон и т.п.)
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    first_name: Mapped[str] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    username: Mapped[str | None] = mapped_column(String(64))
    language_code: Mapped[str | None] = mapped_column(String(16))
    # Фото: telegram — берём из Telegram и обновляем, custom — человек загрузил своё,
    # none — убрал фото, показываем инициалы
    avatar_mode: Mapped[str] = mapped_column(
        String(16), default="telegram", server_default="telegram"
    )
    # Случайный ключ в адресе картинки /api/avatars/<ключ>: меняется с каждым новым фото,
    # поэтому картинку можно кэшировать навсегда. None — фото нет
    avatar_key: Mapped[str | None] = mapped_column(String(32), unique=True)
    # file_unique_id фото в Telegram: если не поменялось, заново не скачиваем
    avatar_telegram_id: Mapped[str | None] = mapped_column(String(64))
    # Когда последний раз спрашивали фото у Telegram
    avatar_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserAvatar(Base):
    """Сама картинка, отдельно от users: users читается почти в каждом запросе."""

    __tablename__ = "user_avatars"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # JPEG до 512 КБ; обычно 15–40 КБ
    data: Mapped[bytes] = mapped_column(LargeBinary)


class Trainer(TimestampMixin, Base):
    """Профиль тренера. Есть строка и is_active — значит, у пользователя есть бета-доступ."""

    __tablename__ = "trainers"
    __table_args__ = (
        CheckConstraint("slot_step_min IN (0, 5, 10, 15, 20, 30, 60)", name="slot_step"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    # Как тренера видят клиенты; по умолчанию имя из Telegram
    display_name: Mapped[str] = mapped_column(String(128))
    timezone: Mapped[str] = mapped_column(
        String(64), default=DEFAULT_TIMEZONE, server_default=DEFAULT_TIMEZONE
    )
    # Адрес зала по умолчанию для услуг
    address: Mapped[str | None] = mapped_column(String(256))
    # Код персональной ссылки для клиентов: t.me/бот?start=c_<код>
    invite_code: Mapped[str] = mapped_column(String(32), unique=True)
    # Записи подтверждаются сразу или после одобрения тренера
    auto_confirm: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    # Шаг, с которым клиенту предлагается время начала, в минутах; 0 — длительность услуги
    slot_step_min: Mapped[int] = mapped_column(Integer, default=15, server_default=text("15"))
    # За сколько часов до начала клиент ещё может отменить запись сам
    cancel_hours: Mapped[int] = mapped_column(Integer, default=12, server_default=text("12"))
    # Админ может отключить тренера; данные при этом сохраняются
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    # Когда тренер прошёл первую настройку в Mini App; None — ещё не прошёл
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Правила занятий: клиент подтверждает их перед первой записью; None — правил нет
    rules: Mapped[str | None] = mapped_column(Text)
    # Когда правила последний раз менялись: принятые раньше клиенты подтверждают снова
    rules_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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


class ScheduleDay(TimestampMixin, Base):
    """Часы на конкретную дату. Полностью заменяют недельный шаблон в этот день.

    windows — список {"start": "10:00", "end": "14:00", "service_ids": [...]}; пустой
    список — выходной. Окна хранятся одним полем: день всегда меняется целиком.
    """

    __tablename__ = "schedule_days"
    __table_args__ = (UniqueConstraint("trainer_id", "day", name="uq_schedule_days_trainer_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    trainer_id: Mapped[int] = mapped_column(
        ForeignKey("trainers.id", ondelete="CASCADE"), index=True
    )
    day: Mapped[date] = mapped_column(Date)
    windows: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)


class TrainerClient(TimestampMixin, Base):
    """Клиент тренера: появляется, когда человек открывает ссылку тренера."""

    __tablename__ = "trainer_clients"
    __table_args__ = (UniqueConstraint("trainer_id", "user_id", name="uq_trainer_clients_pair"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    trainer_id: Mapped[int] = mapped_column(ForeignKey("trainers.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Заметки тренера о клиенте; клиент их не видит
    notes: Mapped[str | None] = mapped_column(Text)
    # Когда клиент согласился с правилами тренера; None — ещё не соглашался
    rules_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(lazy="joined")
    trainer: Mapped[Trainer] = relationship(lazy="joined")

    @property
    def rules_pending(self) -> bool:
        """У тренера есть правила, а клиент их ещё не принял или они с тех пор менялись."""
        updated = self.trainer.rules_updated_at
        if not self.trainer.rules or updated is None:
            return False
        return self.rules_accepted_at is None or self.rules_accepted_at < updated


# Записи, которые занимают время тренера. Отменённые и отклонённые остаются для истории
ACTIVE_BOOKING_STATUSES = ("pending", "confirmed")


class Booking(TimestampMixin, Base):
    """Запись клиента на занятие."""

    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("starts_at < ends_at", name="time_order"),
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'declined', 'cancelled')", name="status"
        ),
        CheckConstraint("created_by IN ('client', 'trainer')", name="created_by"),
        CheckConstraint(
            "cancelled_by IS NULL OR cancelled_by IN ('client', 'trainer')", name="cancelled_by"
        ),
        CheckConstraint(
            "attendance IS NULL OR attendance IN ('attended', 'missed_charged', 'missed_free')",
            name="attendance",
        ),
        CheckConstraint(
            "rescheduled_by IS NULL OR rescheduled_by IN ('client', 'trainer')",
            name="rescheduled_by",
        ),
        Index("ix_bookings_trainer_starts", "trainer_id", "starts_at"),
        Index("ix_bookings_client_starts", "client_id", "starts_at"),
        # Последний рубеж от двойной записи одного клиента на одно занятие.
        # Пересечения и вместимость проверяет сервис под блокировкой строки тренера
        Index(
            "uq_bookings_client_session",
            "client_id",
            "service_id",
            "starts_at",
            unique=True,
            postgresql_where=text("status IN ('pending', 'confirmed')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trainer_id: Mapped[int] = mapped_column(ForeignKey("trainers.id", ondelete="CASCADE"))
    # Клиент — пользователь; связь с тренером лежит в trainer_clients
    client_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # Услуги не удаляются, только выключаются. NO ACTION, а не RESTRICT: проверка в конце
    # запроса, поэтому каскадное удаление тренера убирает и записи, и услуги
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # pending — ждёт тренера, confirmed — подтверждена, declined — тренер отклонил,
    # cancelled — отменена клиентом или тренером
    status: Mapped[str] = mapped_column(String(16))
    # Кто записал: клиент сам или тренер за него
    created_by: Mapped[str] = mapped_column(String(16))
    cancelled_by: Mapped[str | None] = mapped_column(String(16))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Необязательный комментарий того, кто отменил или отклонил запись: «заболел»
    cancel_comment: Mapped[str | None] = mapped_column(Text)
    # Последний перенос: прежнее время начала, кто и когда перенёс, с каким комментарием.
    # Перенос меняет время этой же записи, поэтому блоки и история не теряют связь с ней
    rescheduled_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rescheduled_by: Mapped[str | None] = mapped_column(String(16))
    rescheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reschedule_comment: Mapped[str | None] = mapped_column(Text)
    # Отметка тренера после занятия: attended — прошла, missed_charged — пропуск со списанием,
    # missed_free — пропуск без списания. None — ещё не отмечено
    attendance: Mapped[str | None] = mapped_column(String(16))
    attendance_marked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    client: Mapped[User] = relationship(lazy="joined")
    service: Mapped[Service] = relationship(lazy="joined")
    trainer: Mapped[Trainer] = relationship(lazy="joined")


class PackageTemplate(TimestampMixin, Base):
    """Шаблон блока, чтобы не вводить каждый раз: «10 персональных за 20 000»."""

    __tablename__ = "package_templates"
    __table_args__ = (
        CheckConstraint("sessions_count BETWEEN 1 AND 200", name="sessions_count"),
        CheckConstraint("price >= 0", name="price"),
        CheckConstraint("valid_days IS NULL OR valid_days >= 1", name="valid_days"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trainer_id: Mapped[int] = mapped_column(
        ForeignKey("trainers.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    # Пусто — блок подходит к любой услуге тренера
    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id"))
    sessions_count: Mapped[int] = mapped_column(Integer)
    price: Mapped[int] = mapped_column(Integer)
    # Сколько дней действует блок с даты покупки; пусто — бессрочно
    valid_days: Mapped[int | None] = mapped_column(Integer)

    service: Mapped[Service | None] = relationship(lazy="joined")


class Package(TimestampMixin, Base):
    """Купленный клиентом блок. Поля копируются из шаблона, чтобы правка шаблона его не меняла."""

    __tablename__ = "packages"
    __table_args__ = (
        CheckConstraint("sessions_count BETWEEN 1 AND 200", name="sessions_count"),
        CheckConstraint("price >= 0", name="price"),
        Index("ix_packages_trainer_client", "trainer_id", "client_id"),
        Index("ix_packages_client", "client_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trainer_id: Mapped[int] = mapped_column(ForeignKey("trainers.id", ondelete="CASCADE"))
    client_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(128))
    # Пусто — списывается за любую услугу
    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id"))
    sessions_count: Mapped[int] = mapped_column(Integer)
    # Полная стоимость блока в рублях; оплаты — в payments
    price: Mapped[int] = mapped_column(Integer)
    purchased_on: Mapped[date] = mapped_column(Date)
    # Последний день, когда из блока можно списать занятие; пусто — бессрочно
    valid_until: Mapped[date | None] = mapped_column(Date)
    # Тренер закрыл блок досрочно: из него больше не списывается
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    service: Mapped[Service | None] = relationship(lazy="joined")
    trainer: Mapped[Trainer] = relationship(lazy="joined")
    sessions: Mapped[list["PackageSession"]] = relationship(
        lazy="selectin",
        order_by="(PackageSession.day, PackageSession.id)",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    payments: Mapped[list["Payment"]] = relationship(
        lazy="selectin",
        order_by="(Payment.paid_on, Payment.id)",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class PackageSession(TimestampMixin, Base):
    """Списанное из блока занятие. Номер 1…N не храним: он считается по порядку дат."""

    __tablename__ = "package_sessions"
    __table_args__ = (CheckConstraint("status IN ('attended', 'missed_charged')", name="status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(
        ForeignKey("packages.id", ondelete="CASCADE"), index=True
    )
    # Запись, за которую списано; пусто — тренер отметил занятие в блоке вручную.
    # Уникальность: одна запись списывается не больше одного раза
    booking_id: Mapped[int | None] = mapped_column(
        ForeignKey("bookings.id", ondelete="SET NULL"), unique=True
    )
    day: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16))


class Payment(TimestampMixin, Base):
    """Внесённые за блок деньги. Только учёт: через бот деньги не идут."""

    __tablename__ = "payments"
    __table_args__ = (CheckConstraint("amount > 0", name="amount"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(
        ForeignKey("packages.id", ondelete="CASCADE"), index=True
    )
    amount: Mapped[int] = mapped_column(Integer)
    paid_on: Mapped[date] = mapped_column(Date)
    comment: Mapped[str | None] = mapped_column(String(256))


class ReminderSetting(TimestampMixin, Base):
    """Настройки напоминаний человека в одной роли. Нет строки — действуют значения по умолчанию.

    Тренер, который сам записан к другому тренеру, настраивает обе роли отдельно.
    """

    __tablename__ = "reminder_settings"
    __table_args__ = (
        UniqueConstraint("user_id", "role", name="uq_reminder_settings_user_role"),
        CheckConstraint("role IN ('client', 'trainer')", name="role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))
    enabled: Mapped[bool] = mapped_column(Boolean)
    # За сколько минут до начала напомнить, например [1440, 120]
    offsets: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    # Только у тренера: после занятия попросить отметить его
    attendance_prompt: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )


class Notification(Base):
    """Очередь уведомлений. Строка — одно сообщение одному человеку.

    Отправщик забирает строки через SELECT ... FOR UPDATE SKIP LOCKED и ставит sent_at
    в той же транзакции, поэтому перезапуск или второй экземпляр не отправят её дважды.
    dedup_key не даёт поставить в очередь одно и то же сообщение второй раз.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'sent', 'skipped', 'failed')", name="status"),
        # Отправщик ищет только ожидающие строки, их немного
        Index(
            "ix_notifications_due",
            "send_at",
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_notifications_booking", "booking_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Что за сообщение: new_booking, reminder и т.д.; текст собирается при отправке
    kind: Mapped[str] = mapped_column(String(32))
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"))
    package_id: Mapped[int | None] = mapped_column(ForeignKey("packages.id", ondelete="CASCADE"))
    # Подробности, которых нет в записи: для напоминания — роль и смещение
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    dedup_key: Mapped[str] = mapped_column(String(128), unique=True)
    send_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # pending — ждёт отправки, sent — отправлено, skipped — уже не нужно (запись отменили,
    # занятие прошло), failed — доставить нельзя (человек заблокировал бота)
    status: Mapped[str] = mapped_column(
        String(16), default="pending", server_default=text("'pending'")
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
