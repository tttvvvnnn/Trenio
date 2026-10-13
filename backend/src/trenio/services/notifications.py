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

from trenio.db.models import Booking, Notification, ReminderSetting, Trainer, User


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
    # Напоминание о занятии клиенту или тренеру, payload: role и offset
    REMINDER = "reminder"


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


# Клиенту по умолчанию напоминаем за сутки и за 2 часа. Тренеру — нет: при восьми занятиях
# в день это восемь сообщений, пусть включит сам
DEFAULT_PREFS = {
    Role.CLIENT: ReminderPrefs(enabled=True, offsets=[1440, 120]),
    Role.TRAINER: ReminderPrefs(enabled=False, offsets=[60]),
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
    session: AsyncSession, kind: Kind, booking: Booking, user_id: int, now: datetime
) -> None:
    await _enqueue(
        session,
        user_id=user_id,
        kind=kind,
        dedup_key=f"{kind.value}:{booking.id}",
        send_at=now,
        booking_id=booking.id,
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
    await _event(session, Kind.BOOKING_CONFIRMED, booking, booking.client_id, now)
    await schedule_reminders(session, booking, now)


async def booking_declined(session: AsyncSession, booking: Booking, now: datetime) -> None:
    await _event(session, Kind.BOOKING_DECLINED, booking, booking.client_id, now)
    await drop_reminders(session, booking.id)


async def booking_cancelled(
    session: AsyncSession, booking: Booking, by: Role, now: datetime
) -> None:
    if by is Role.CLIENT:
        trainer_user_id = await _trainer_user_id(session, booking)
        await _event(session, Kind.CLIENT_CANCELLED, booking, trainer_user_id, now)
    else:
        await _event(session, Kind.TRAINER_CANCELLED, booking, booking.client_id, now)
    await drop_reminders(session, booking.id)


async def drop_reminders(session: AsyncSession, booking_id: int) -> None:
    """Убирает неотправленные напоминания об отменённой записи."""
    await session.execute(
        delete(Notification).where(
            Notification.booking_id == booking_id,
            Notification.kind == Kind.REMINDER,
            Notification.status == Status.PENDING,
        )
    )


async def schedule_reminders(
    session: AsyncSession, booking: Booking, now: datetime, roles: tuple[Role, ...] = tuple(Role)
) -> None:
    """Ставит напоминания о подтверждённой записи по настройкам клиента и тренера.

    Время, которое уже прошло, пропускаем: записались за час — напоминание «за 2 часа» не нужно.
    """
    recipients = {Role.CLIENT: booking.client_id}
    if Role.TRAINER in roles:
        recipients[Role.TRAINER] = await _trainer_user_id(session, booking)
    for role in roles:
        user_id = recipients[role]
        prefs = await get_prefs(session, user_id, role)
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


# --- Настройки напоминаний ---


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
