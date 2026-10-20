"""Очередь уведомлений: что и когда отправить. Отправляет trenio.delivery.

Уведомление кладётся в очередь в той же транзакции, что и изменение записи: если сервис
упадёт сразу после сохранения, сообщение не потеряется. Текст собирается при отправке
из свежих данных, поэтому в очереди только тип, получатель и время.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.db.models import (
    Booking,
    Notification,
    Package,
    ReminderSetting,
    SubscriptionPayment,
    Trainer,
    User,
)


class Kind(StrEnum):
    # Тренеру: клиент записался
    NEW_BOOKING = "new_booking"
    # Тренеру: клиент отменил запись
    CLIENT_CANCELLED = "client_cancelled"
    # Клиенту: тренер записал его сам
    TRAINER_BOOKED = "trainer_booked"
    # Клиенту: тренер подтвердил или отклонил запись
    BOOKING_CONFIRMED = "booking_confirmed"
    BOOKING_DECLINED = "booking_declined"
    # Клиенту: тренер отменил запись
    TRAINER_CANCELLED = "trainer_cancelled"
    # Второй стороне: запись перенесли, payload: by, from и to (время до и после, ISO)
    BOOKING_RESCHEDULED = "booking_rescheduled"
    # Напоминание о занятии клиенту или тренеру, payload: role и offset
    REMINDER = "reminder"
    # Тренеру после занятия: отметьте, прошло ли оно
    ATTENDANCE_PROMPT = "attendance_prompt"
    # Клиенту и тренеру: в блоке осталось мало занятий или он закончился, payload: role и left
    PACKAGE_LEFT = "package_left"
    # Клиенту и тренеру: срок блока скоро кончится, а занятия ещё остались.
    # payload: role, days и valid_until (дата окончания, по которой ставили)
    PACKAGE_EXPIRING = "package_expiring"
    # Тренеру: по его личной ссылке пришёл новый тренер, payload: trainer_id
    TRAINER_JOINED = "trainer_joined"
    # Тренеру: Pro или пробный период скоро закончится или закончился.
    # payload: until (момент окончания, ISO) и days (за сколько дней предупреждаем)
    SUBSCRIPTION_ENDING = "subscription_ending"
    # Тренеру: на бесплатном тарифе к нему не смог присоединиться клиент, payload: user_id
    CLIENT_LIMIT = "client_limit"
    # Тренеру: оплата Pro прошла, payload: payment_id
    SUBSCRIPTION_PAID = "subscription_paid"
    # Тренеру: приглашённый им тренер оплатил Pro, payload: payment_id и bonus (рубли)
    REFERRAL_BONUS = "referral_bonus"
    # Тренеру: рассылка из админки, payload: broadcast_id
    BROADCAST = "broadcast"


# Уведомления о будущем занятии: при отмене записи они больше не нужны
UPCOMING_KINDS = (Kind.REMINDER, Kind.ATTENDANCE_PROMPT)
# При скольких оставшихся занятиях предупреждаем; 0 — блок закончился
PACKAGE_LEFT_ALERTS = frozenset({2, 1, 0})
# За сколько дней до конца срока блока предупреждаем, если в нём остались занятия
PACKAGE_EXPIRY_ALERTS = (7, 1)


class Role(StrEnum):
    CLIENT = "client"
    TRAINER = "trainer"


class Status(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True)
class ReminderPrefs:
    enabled: bool
    # За сколько минут до начала напомнить, по убыванию
    offsets: list[int] = field(default_factory=list)
    # Только у тренера: после занятия попросить отметить его
    attendance_prompt: bool = True


# По умолчанию все уведомления включены: клиенту напоминаем за сутки и за 2 часа,
# тренеру — за час. Кому много, выключит в профиле
DEFAULT_PREFS = {
    Role.CLIENT: ReminderPrefs(enabled=True, offsets=[1440, 120]),
    Role.TRAINER: ReminderPrefs(enabled=True, offsets=[60]),
}


async def _enqueue(
    session: AsyncSession,
    *,
    user_id: int,
    kind: Kind,
    dedup_key: str,
    send_at: datetime,
    booking_id: int | None = None,
    package_id: int | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    # Повтор с тем же ключом молча пропускается: одно и то же сообщение дважды не встанет
    stmt = (
        insert(Notification)
        .values(
            user_id=user_id,
            kind=kind.value,
            dedup_key=dedup_key,
            send_at=send_at,
            booking_id=booking_id,
            package_id=package_id,
            payload=payload or {},
        )
        .on_conflict_do_nothing(index_elements=["dedup_key"])
    )
    await session.execute(stmt)


async def _event(
    session: AsyncSession,
    kind: Kind,
    booking: Booking,
    user_id: int,
    now: datetime,
    *,
    repeatable: bool = False,
    payload: dict[str, Any] | None = None,
) -> None:
    # Повторяемое событие (перенос, подтверждение после переноса) может случиться с записью
    # не раз: ключ отличаем временем события
    suffix = f":{now.timestamp():.0f}" if repeatable else ""
    await _enqueue(
        session,
        user_id=user_id,
        kind=kind,
        dedup_key=f"{kind.value}:{booking.id}{suffix}",
        send_at=now,
        booking_id=booking.id,
        payload=payload,
    )


async def _trainer_user_id(session: AsyncSession, booking: Booking) -> int:
    user_id = await session.scalar(select(Trainer.user_id).where(Trainer.id == booking.trainer_id))
    assert user_id is not None
    return user_id


async def booking_created(session: AsyncSession, booking: Booking, now: datetime) -> None:
    """Новая запись: сообщить второй стороне и запланировать напоминания."""
    trainer_user_id = await _trainer_user_id(session, booking)
    if booking.created_by == Role.CLIENT:
        await _event(session, Kind.NEW_BOOKING, booking, trainer_user_id, now)
    else:
        await _event(session, Kind.TRAINER_BOOKED, booking, booking.client_id, now)
    if booking.status == "confirmed":
        await schedule_reminders(session, booking, now)


async def booking_confirmed(session: AsyncSession, booking: Booking, now: datetime) -> None:
    # Перенесённую клиентом запись тренер подтверждает ещё раз
    await _event(session, Kind.BOOKING_CONFIRMED, booking, booking.client_id, now, repeatable=True)
    await schedule_reminders(session, booking, now)


async def booking_declined(session: AsyncSession, booking: Booking, now: datetime) -> None:
    await _event(session, Kind.BOOKING_DECLINED, booking, booking.client_id, now)
    await drop_upcoming(session, booking.id)


async def booking_cancelled(
    session: AsyncSession, booking: Booking, by: Role, now: datetime
) -> None:
    if by is Role.CLIENT:
        trainer_user_id = await _trainer_user_id(session, booking)
        await _event(session, Kind.CLIENT_CANCELLED, booking, trainer_user_id, now)
    else:
        await _event(session, Kind.TRAINER_CANCELLED, booking, booking.client_id, now)
    await drop_upcoming(session, booking.id)


async def booking_rescheduled(
    session: AsyncSession, booking: Booking, by: Role, previous: datetime, now: datetime
) -> None:
    """Перенос: сообщить второй стороне и поставить напоминания под новое время."""
    if by is Role.CLIENT:
        user_id = await _trainer_user_id(session, booking)
    else:
        user_id = booking.client_id
    payload = {
        "by": by.value,
        "from": previous.isoformat(),
        "to": booking.starts_at.isoformat(),
    }
    await _event(
        session, Kind.BOOKING_RESCHEDULED, booking, user_id, now, repeatable=True, payload=payload
    )
    # Напоминания о прежнем времени, даже уже отправленные, больше ни о чём: убираем их,
    # иначе ключи дедупликации не дадут поставить напоминания о новом времени
    await session.execute(
        delete(Notification).where(
            Notification.booking_id == booking.id, Notification.kind == Kind.REMINDER
        )
    )
    await drop_upcoming(session, booking.id)
    if booking.status == "confirmed":
        await schedule_reminders(session, booking, now)


async def booking_retimed(session: AsyncSession, booking: Booking, now: datetime) -> None:
    """Поменялось время окончания: просьба отметить занятие приходит к новому концу."""
    await session.execute(
        delete(Notification).where(
            Notification.booking_id == booking.id,
            Notification.kind == Kind.ATTENDANCE_PROMPT,
            Notification.status == Status.PENDING,
        )
    )
    if booking.status == "confirmed":
        await schedule_reminders(session, booking, now, roles=(Role.TRAINER,))


async def drop_upcoming(session: AsyncSession, booking_id: int) -> None:
    """Убирает неотправленные напоминания и просьбу отметить занятие у отменённой записи."""
    await session.execute(
        delete(Notification).where(
            Notification.booking_id == booking_id,
            Notification.kind.in_(UPCOMING_KINDS),
            Notification.status == Status.PENDING,
        )
    )


async def schedule_reminders(
    session: AsyncSession, booking: Booking, now: datetime, roles: tuple[Role, ...] = tuple(Role)
) -> None:
    """Ставит напоминания о подтверждённой записи по настройкам клиента и тренера.

    Тренеру заодно — просьбу отметить занятие сразу после его окончания.

    Время, которое уже прошло, пропускаем: записались за час — напоминание «за 2 часа» не нужно.
    """
    recipients = {Role.CLIENT: booking.client_id}
    if Role.TRAINER in roles:
        recipients[Role.TRAINER] = await _trainer_user_id(session, booking)
    for role in roles:
        user_id = recipients[role]
        prefs = await get_prefs(session, user_id, role)
        if role is Role.TRAINER and prefs.attendance_prompt:
            await _enqueue(
                session,
                user_id=user_id,
                kind=Kind.ATTENDANCE_PROMPT,
                dedup_key=f"{Kind.ATTENDANCE_PROMPT.value}:{booking.id}",
                send_at=booking.ends_at,
                booking_id=booking.id,
            )
        if not prefs.enabled:
            continue
        for offset in prefs.offsets:
            send_at = booking.starts_at - timedelta(minutes=offset)
            if send_at <= now:
                continue
            await _enqueue(
                session,
                user_id=user_id,
                kind=Kind.REMINDER,
                # Отправленное напоминание не повторится, даже если настройки поменяют туда-обратно
                dedup_key=f"reminder:{booking.id}:{role.value}:{offset}",
                send_at=send_at,
                booking_id=booking.id,
                payload={"role": role.value, "offset": offset},
            )


async def package_left(session: AsyncSession, package: Package, left: int, now: datetime) -> None:
    """После списания занятия: предупредить клиента и тренера, что блок заканчивается.

    Каждое отправленное предупреждение — один раз на блок: снятая и поставленная заново
    отметка не пришлёт «осталось 2 занятия» второй раз.
    """
    if left not in PACKAGE_LEFT_ALERTS:
        return
    trainer_user_id = await session.scalar(
        select(Trainer.user_id).where(Trainer.id == package.trainer_id)
    )
    assert trainer_user_id is not None
    for role, user_id in ((Role.CLIENT, package.client_id), (Role.TRAINER, trainer_user_id)):
        dedup_key = f"{Kind.PACKAGE_LEFT.value}:{package.id}:{role.value}:{left}"
        # Пропущенное как устаревшее (отметку успели снять) не считается: ставим заново
        await session.execute(
            delete(Notification).where(
                Notification.dedup_key == dedup_key, Notification.status == Status.SKIPPED
            )
        )
        await _enqueue(
            session,
            user_id=user_id,
            kind=Kind.PACKAGE_LEFT,
            dedup_key=dedup_key,
            send_at=now,
            package_id=package.id,
            payload={"role": role.value, "left": left},
        )


async def package_expiring(
    session: AsyncSession, package: Package, days: int, send_at: datetime
) -> None:
    """Предупредить клиента и тренера, что срок блока кончается через days дней.

    Ключ с датой окончания: если тренер продлит блок, придёт новое предупреждение,
    а поставленное по старой дате при отправке окажется неверным и пропустится.
    """
    assert package.valid_until is not None
    trainer_user_id = await session.scalar(
        select(Trainer.user_id).where(Trainer.id == package.trainer_id)
    )
    assert trainer_user_id is not None
    until = package.valid_until.isoformat()
    for role, user_id in ((Role.CLIENT, package.client_id), (Role.TRAINER, trainer_user_id)):
        await _enqueue(
            session,
            user_id=user_id,
            kind=Kind.PACKAGE_EXPIRING,
            dedup_key=f"{Kind.PACKAGE_EXPIRING.value}:{package.id}:{role.value}:{days}:{until}",
            send_at=send_at,
            package_id=package.id,
            payload={"role": role.value, "days": days, "valid_until": until},
        )


# --- Настройки напоминаний ---


async def trainer_joined(
    session: AsyncSession, inviter: Trainer, joined: Trainer, now: datetime
) -> None:
    await _enqueue(
        session,
        user_id=inviter.user_id,
        kind=Kind.TRAINER_JOINED,
        dedup_key=f"{Kind.TRAINER_JOINED.value}:{joined.id}",
        send_at=now,
        payload={"trainer_id": joined.id},
    )


async def subscription_ending(
    session: AsyncSession, trainer: Trainer, until: datetime, before: timedelta, at: datetime
) -> None:
    await _enqueue(
        session,
        user_id=trainer.user_id,
        kind=Kind.SUBSCRIPTION_ENDING,
        dedup_key=f"{Kind.SUBSCRIPTION_ENDING.value}:{trainer.id}:{until.timestamp():.0f}:{before.days}",
        send_at=at,
        payload={"until": until.isoformat(), "days": before.days},
    )


async def client_limit(session: AsyncSession, trainer: Trainer, user: User, now: datetime) -> None:
    await _enqueue(
        session,
        user_id=trainer.user_id,
        kind=Kind.CLIENT_LIMIT,
        dedup_key=f"{Kind.CLIENT_LIMIT.value}:{trainer.id}:{user.id}",
        send_at=now,
        payload={"user_id": user.id},
    )


async def subscription_paid(
    session: AsyncSession, trainer: Trainer, payment: SubscriptionPayment, now: datetime
) -> None:
    await _enqueue(
        session,
        user_id=trainer.user_id,
        kind=Kind.SUBSCRIPTION_PAID,
        dedup_key=f"{Kind.SUBSCRIPTION_PAID.value}:{payment.id}",
        send_at=now,
        payload={"payment_id": payment.id},
    )


async def referral_bonus(
    session: AsyncSession, inviter: Trainer, payment: SubscriptionPayment, bonus: int, now: datetime
) -> None:
    await _enqueue(
        session,
        user_id=inviter.user_id,
        kind=Kind.REFERRAL_BONUS,
        dedup_key=f"{Kind.REFERRAL_BONUS.value}:{payment.id}",
        send_at=now,
        payload={"payment_id": payment.id, "bonus": bonus},
    )


async def broadcast(session: AsyncSession, broadcast_id: int, user_id: int, now: datetime) -> None:
    await _enqueue(
        session,
        user_id=user_id,
        kind=Kind.BROADCAST,
        dedup_key=f"{Kind.BROADCAST.value}:{broadcast_id}:{user_id}",
        send_at=now,
        payload={"broadcast_id": broadcast_id},
    )


async def get_prefs(session: AsyncSession, user_id: int, role: Role) -> ReminderPrefs:
    row = await session.scalar(
        select(ReminderSetting).where(
            ReminderSetting.user_id == user_id, ReminderSetting.role == role
        )
    )
    if row is None:
        return DEFAULT_PREFS[role]
    return ReminderPrefs(
        enabled=row.enabled, offsets=list(row.offsets), attendance_prompt=row.attendance_prompt
    )


async def set_prefs(
    session: AsyncSession,
    user: User,
    role: Role,
    prefs: ReminderPrefs,
    now: datetime,
    trainer: Trainer | None = None,
) -> ReminderPrefs:
    """Сохраняет настройки и пересчитывает напоминания о будущих записях в этой роли."""
    offsets = sorted(set(prefs.offsets), reverse=True)
    values = {
        "enabled": prefs.enabled,
        "offsets": offsets,
        "attendance_prompt": prefs.attendance_prompt,
    }
    await session.execute(
        insert(ReminderSetting)
        .values(user_id=user.id, role=role.value, **values)
        .on_conflict_do_update(constraint="uq_reminder_settings_user_role", set_=values)
    )
    await session.execute(
        delete(Notification).where(
            Notification.user_id == user.id,
            Notification.kind == Kind.REMINDER,
            Notification.status == Status.PENDING,
            Notification.payload["role"].astext == role.value,
        )
    )
    if role is Role.TRAINER:
        await session.execute(
            delete(Notification).where(
                Notification.user_id == user.id,
                Notification.kind == Kind.ATTENDANCE_PROMPT,
                Notification.status == Status.PENDING,
            )
        )
    if role is Role.CLIENT:
        mine = Booking.client_id == user.id
    else:
        assert trainer is not None
        mine = Booking.trainer_id == trainer.id
    upcoming = await session.scalars(
        select(Booking).where(mine, Booking.status == "confirmed", Booking.starts_at > now)
    )
    for booking in upcoming.all():
        await schedule_reminders(session, booking, now, roles=(role,))
    await session.commit()
    return ReminderPrefs(prefs.enabled, offsets, prefs.attendance_prompt)
