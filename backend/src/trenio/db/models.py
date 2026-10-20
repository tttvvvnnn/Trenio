"""Модели таблиц. Добавляются по этапам вместе с миграциями."""

from datetime import date, datetime, time
from decimal import Decimal
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
    Numeric,
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
    # Имя, которое видят другие: из Telegram или своё, если человек его поменял
    first_name: Mapped[str] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    # True — имя задано в профиле, Telegram его больше не перезаписывает
    name_custom: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    # Имя из Telegram на последний вход: к нему возвращаемся, если своё сбросили
    telegram_first_name: Mapped[str | None] = mapped_column(String(128))
    telegram_last_name: Mapped[str | None] = mapped_column(String(128))
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
    # Когда человек последний раз открывал Mini App: для активности в админ-панели
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Когда человек прошёл или пропустил вводный тур; None — показать при входе.
    # У тренера и клиента туры свои: тренер может ещё и записываться к другому тренеру
    trainer_tour_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    client_tour_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Клиент без Telegram, которого завёл тренер: имя правит тренер, уведомления не уходят.
    # Когда клиент привяжет Telegram, эта строка сливается с его аккаунтом и удаляется
    created_by_trainer_id: Mapped[int | None] = mapped_column(
        ForeignKey("trainers.id", ondelete="SET NULL", use_alter=True)
    )
    # Согласие на обработку персональных данных: когда и с какой версией политики
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_version: Mapped[int | None] = mapped_column(Integer)
    # Человек удалил аккаунт: строка обезличена и осталась только ради учёта у тренеров
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def is_offline(self) -> bool:
        return self.telegram_id is None

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class UserAvatar(Base):
    """Сама картинка, отдельно от users: users читается почти в каждом запросе."""

    __tablename__ = "user_avatars"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # JPEG до 512 КБ; обычно 15–40 КБ
    data: Mapped[bytes] = mapped_column(LargeBinary)


class UserActivityDay(Base):
    """День, когда человек открывал приложение: для активности тренеров в админке."""

    __tablename__ = "user_activity_days"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # День по Москве, как и вся статистика админки
    day: Mapped[date] = mapped_column(Date, primary_key=True)


class AppSetting(Base):
    """Настройки, которые админ меняет в админ-панели без деплоя. Значение — JSON."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


MAIN_BOT_ID = 1


class Bot(TimestampMixin, Base):
    """Бот, через который специалист и его клиенты работают с Trenio.

    Пока бот один — основной, его строку создаёт миграция, а токен берётся из BOT_TOKEN.
    Таблица нужна заранее: админка и статистика сразу делят данные по bot_id, и при
    подключении своих ботов специалистов ничего не придётся переписывать.
    """

    __tablename__ = "bots"
    __table_args__ = (
        CheckConstraint("platform IN ('telegram')", name="platform"),
        UniqueConstraint("platform", "external_id", name="uq_bots_platform_external_id"),
        # Основной бот ровно один: через него идут админ-команды, отчёты и бэкап
        Index("uq_bots_main", "is_main", unique=True, postgresql_where=text("is_main")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(16), default="telegram", server_default="telegram")
    # id бота в мессенджере; у основного приложение записывает его при старте (getMe)
    external_id: Mapped[int | None] = mapped_column(BigInteger)
    username: Mapped[str | None] = mapped_column(String(64))
    # Токен, зашифрованный ключом из окружения. У основного бота пусто: токен в BOT_TOKEN
    token_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    # Короткое имя для адреса Mini App (?bot=<slug>)
    slug: Mapped[str] = mapped_column(String(32), unique=True)
    # Направление специалистов бота: от него зависят слова в интерфейсе и модули
    vertical: Mapped[str] = mapped_column(String(16), default="fitness", server_default="fitness")
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    is_main: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    # Выключенный бот не принимает обновления и не рассылает уведомления
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    # До какого дня оплачен свой бот; у основного не используется
    paid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def _main_bot_fk(nullable: bool = False) -> Mapped[Any]:
    # Пока маршрутизации по ботам нет, всё новое относится к основному. Значение по умолчанию
    # в Python, а не в базе: когда появятся свои боты, его уберём, и забытый bot_id станет ошибкой
    return mapped_column(
        ForeignKey("bots.id", ondelete="RESTRICT"),
        default=MAIN_BOT_ID,
        nullable=nullable,
        index=True,
    )


class AdminSession(Base):
    """Вход в веб-админку. Действует, только когда админ подтвердил его кнопкой в боте."""

    __tablename__ = "admin_sessions"
    __table_args__ = (CheckConstraint("status IN ('pending', 'active', 'denied')", name="status"),)

    # Случайный id, он же лежит в токене куки
    id: Mapped[str] = mapped_column(String(43), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    # Сверяется с заголовком X-CSRF-Token у запросов, которые что-то меняют
    csrf_token: Mapped[str] = mapped_column(String(43))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdminAuditEntry(Base):
    """Журнал действий в админке. Строки только добавляются: изменить или удалить их
    не даёт триггер в базе. Поэтому и без внешних ключей: удаление пользователя
    не должно трогать журнал."""

    __tablename__ = "admin_audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer)
    session_id: Mapped[str | None] = mapped_column(String(43))
    # Что сделано, например login.confirmed или trainer.disabled
    action: Mapped[str] = mapped_column(String(64))
    # С чем: «trainer:12», «session:…»
    target: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Broadcast(Base):
    """Рассылка тренерам из админки. Сами сообщения — строки notifications с kind broadcast."""

    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = _main_bot_fk()
    # Кнопка «Открыть Trenio» под сообщением. Выше поля text: оно перекрывает sqlalchemy.text
    with_button: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    text: Mapped[str] = mapped_column(Text)
    # Кому: all, trial, free, pro, not_set_up, quiet; см. trenio.services.broadcasts
    segment: Mapped[str] = mapped_column(String(32))
    recipients: Mapped[int] = mapped_column(Integer)
    # Кто отправил; без внешнего ключа, как в журнале действий
    created_by: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PromoView(Base):
    """Что человек сделал с промо-предложением: для счётчиков в админке
    и чтобы карточка на главном экране больше не появлялась после закрытия."""

    __tablename__ = "promo_views"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # Карточку впервые показали на главном экране
    shown_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Закрыл карточку крестиком
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Открыл экран с промокодом
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Нажал кнопку перехода в бота
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ClientError(Base):
    """Ошибка из Mini App: для ленты и строки «Состояние» в админке. Хранится 90 дней."""

    __tablename__ = "client_errors"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Из какого бота открыли Mini App
    bot_id: Mapped[int | None] = _main_bot_fk(nullable=True)
    message: Mapped[str] = mapped_column(String(500))
    # Где случилось: компонент или «window»
    screen: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Trainer(TimestampMixin, Base):
    """Профиль тренера. Есть строка и is_active — значит, у пользователя есть бета-доступ."""

    __tablename__ = "trainers"
    __table_args__ = (
        CheckConstraint("slot_step_min IN (0, 5, 10, 15, 20, 30, 60)", name="slot_step"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    # Бот, в котором работают тренер и его клиенты
    bot_id: Mapped[int] = _main_bot_fk()
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
    # Запись клиента без блока: allow — разрешать, confirm — только с подтверждением тренера,
    # forbid — запрещать. Тренера, который записывает сам, правило не ограничивает
    one_off_mode: Mapped[str] = mapped_column(
        String(16), default="allow", server_default=text("'allow'")
    )
    # Код личной ссылки, по которой тренер приглашает других тренеров: t.me/бот?start=r_<код>
    referral_code: Mapped[str] = mapped_column(String(32), unique=True)
    # Тренер, по чьей ссылке пришёл этот; None — пришёл по ссылке админа или сам админ
    referred_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("trainers.id", ondelete="SET NULL"), index=True
    )
    # Конец пробного периода и оплаченного Pro. После обоих тренер на бесплатном тарифе:
    # не больше трёх клиентов. Подробнее в trenio.services.subscription
    trial_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pro_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Баланс в рублях: 20% с оплат приглашённых тренеров. Тратится только на подписку,
    # история — в balance_entries
    balance: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))

    user: Mapped[User] = relationship(lazy="joined", foreign_keys=[user_id])


class TrainerInvite(TimestampMixin, Base):
    """Одноразовая ссылка, по которой админ выдаёт человеку доступ тренера."""

    __tablename__ = "trainer_invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    # Бот, в котором приглашение действует
    bot_id: Mapped[int] = _main_bot_fk()
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SubscriptionPayment(TimestampMixin, Base):
    """Оплата Pro: часть списывается с баланса, остальное — через Platega по СБП."""

    __tablename__ = "subscription_payments"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'paid', 'canceled')", name="status"),
        CheckConstraint("amount >= 0 AND balance_used >= 0", name="amounts"),
        Index(
            "ix_subscription_payments_pending",
            "created_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trainer_id: Mapped[int] = mapped_column(
        ForeignKey("trainers.id", ondelete="CASCADE"), index=True
    )
    # Через какой бот пришла оплата: деньги общие, но в отчёте видно источник
    bot_id: Mapped[int] = _main_bot_fk()
    # month или year, см. trenio.services.subscription.plans
    plan: Mapped[str] = mapped_column(String(16))
    days: Mapped[int] = mapped_column(Integer)
    # Цена тарифа = amount + balance_used, в рублях
    price: Mapped[int] = mapped_column(Integer)
    # Сколько платится деньгами через Platega; 0 — всё покрыл баланс
    amount: Mapped[int] = mapped_column(Integer)
    # Сколько списано с баланса; при отмене возвращается
    balance_used: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    transaction_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    # Страница оплаты Platega: открыть ещё раз, если человек закрыл её
    redirect_url: Mapped[str | None] = mapped_column(Text)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PromoCode(Base):
    """Промокод для тренеров: скидка на одну оплату Pro или дни Pro бесплатно."""

    __tablename__ = "promo_codes"
    __table_args__ = (
        CheckConstraint("kind IN ('percent', 'rubles', 'days')", name="kind"),
        CheckConstraint("value > 0", name="value"),
        CheckConstraint("max_uses IS NULL OR max_uses > 0", name="max_uses"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = _main_bot_fk()
    # Всегда в верхнем регистре: тренер может ввести как угодно
    code: Mapped[str] = mapped_column(String(32), unique=True)
    # percent — скидка в процентах, rubles — в рублях, days — дни Pro без оплаты
    kind: Mapped[str] = mapped_column(String(16))
    value: Mapped[int] = mapped_column(Integer)
    # Сколько тренеров могут воспользоваться; None — без ограничения. Каждый — один раз
    max_uses: Mapped[int | None] = mapped_column(Integer)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Для себя: кому и зачем выдан
    note: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PromoRedemption(Base):
    """Тренер ввёл промокод. Скидка ждёт оплаты (reserved), дни Pro даются сразу (used)."""

    __tablename__ = "promo_redemptions"
    __table_args__ = (
        CheckConstraint("status IN ('reserved', 'used')", name="status"),
        UniqueConstraint("code_id", "trainer_id", name="uq_promo_redemptions_pair"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code_id: Mapped[int] = mapped_column(ForeignKey("promo_codes.id", ondelete="CASCADE"))
    trainer_id: Mapped[int] = mapped_column(
        ForeignKey("trainers.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(16))
    # Оплата, в которой применилась скидка
    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscription_payments.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    code: Mapped[PromoCode] = relationship(lazy="joined")


class BalanceEntry(Base):
    """Движение по балансу тренера: начисление за приглашённого, оплата, возврат."""

    __tablename__ = "balance_entries"
    __table_args__ = (CheckConstraint("kind IN ('referral', 'payment', 'refund')", name="kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    trainer_id: Mapped[int] = mapped_column(
        ForeignKey("trainers.id", ondelete="CASCADE"), index=True
    )
    # Плюс — начисление, минус — списание
    amount: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16))
    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscription_payments.id", ondelete="SET NULL")
    )
    # За чью оплату начислено: приглашённый тренер
    from_trainer_id: Mapped[int | None] = mapped_column(
        ForeignKey("trainers.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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
    # Код личной ссылки, по которой клиент без Telegram привязывает свой аккаунт
    claim_code: Mapped[str | None] = mapped_column(String(32), unique=True)
    # Телефон клиента: видит только этот тренер. Хранится, только если клиент согласился
    phone: Mapped[str | None] = mapped_column(String(32))
    phone_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(lazy="joined")
    trainer: Mapped[Trainer] = relationship(lazy="joined")

    @property
    def rules_pending(self) -> bool:
        """У тренера есть правила, а клиент их ещё не принял или они с тех пор менялись."""
        updated = self.trainer.rules_updated_at
        if not self.trainer.rules or updated is None:
            return False
        return self.rules_accepted_at is None or self.rules_accepted_at < updated


class ClientMeasurement(TimestampMixin, Base):
    """Замер клиента у тренера: вес, обхваты или свой вид. Один замер вида в день."""

    __tablename__ = "client_measurements"
    __table_args__ = (
        CheckConstraint("value > 0", name="value"),
        Index("ix_client_measurements_link_day", "trainer_client_id", "day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Замеры принадлежат паре тренер–клиент: у другого тренера клиент их не увидит
    trainer_client_id: Mapped[int] = mapped_column(
        ForeignKey("trainer_clients.id", ondelete="CASCADE")
    )
    day: Mapped[date] = mapped_column(Date)
    # weight, waist, chest, hips или custom — свой вид с названием и единицей
    kind: Mapped[str] = mapped_column(String(16))
    label: Mapped[str | None] = mapped_column(String(48))
    unit: Mapped[str | None] = mapped_column(String(16))
    value: Mapped[Decimal] = mapped_column(Numeric(8, 2))


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
        CheckConstraint("price IS NULL OR price >= 0", name="price"),
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
    # Цена этого занятия, если оно разовое: при записи копируется из услуги, тренер может
    # поставить свою. None — у услуги цены не было. Занятие из блока стоит долю блока
    price: Mapped[int | None] = mapped_column(Integer)
    # Тренер решил: не списывать из блока, занятие оплачивается отдельно
    no_package: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    # Заметка тренера к занятию: что делали. Клиент её видит, если она не «только для меня»
    trainer_note: Mapped[str | None] = mapped_column(Text)
    trainer_note_private: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    # Длительность не храним отдельно: это ends_at - starts_at. Тренер может сделать
    # её не такой, как у услуги

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
