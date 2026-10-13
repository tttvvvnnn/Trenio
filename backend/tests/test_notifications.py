"""Уведомления: события о записях, напоминания ровно один раз, настройки."""

import asyncio
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import ADMIN_TELEGRAM_ID
from tests.test_bookings import ELEVEN, TEN, book, new_client, setup_trainer
from trenio.db.models import Notification, User
from trenio.db.session import get_sessionmaker
from trenio.delivery.channel import DeliveryError, OutMessage
from trenio.delivery.sender import Sender, dispatch_due

START = datetime(2030, 1, 7, 7, 0, tzinfo=UTC)  # TEN: пн 7 янв, 10:00 по Москве
CLIENT_TG = 3003


class FakeChannel:
    """Вместо Telegram складывает сообщения в список."""

    def __init__(self, delay: float = 0, error: DeliveryError | None = None) -> None:
        self.sent: list[tuple[int | None, str]] = []
        self.delay = delay
        self.error = error

    async def send(self, user: User, message: OutMessage) -> None:
        await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        self.sent.append((user.telegram_id, message.text))


async def dispatch(channel: FakeChannel, now: datetime) -> int:
    return await dispatch_due(get_sessionmaker(), channel, now)


async def queue(session: AsyncSession) -> list[tuple[int, str, str, str]]:
    """(telegram_id, kind, роль напоминания или '', status) по порядку send_at."""
    rows = await session.execute(
        select(User.telegram_id, Notification.kind, Notification.payload, Notification.status)
        .join(User, User.id == Notification.user_id)
        .order_by(Notification.send_at, Notification.id)
        .execution_options(populate_existing=True)
    )
    return [(tg, kind, payload.get("role", ""), st) for tg, kind, payload, st in rows.all()]


async def reminder_times(session: AsyncSession) -> list[datetime]:
    rows = await session.scalars(
        select(Notification.send_at)
        .where(Notification.kind == "reminder", Notification.status == "pending")
        .order_by(Notification.send_at)
    )
    return list(rows.all())


async def test_client_books_trainer_is_told(client: AsyncClient, session: AsyncSession) -> None:
    _, trainer_id, service_id = await setup_trainer(client)
    headers = await new_client(client, session, trainer_id, CLIENT_TG)
    code, _ = await book(client, headers, trainer_id, service_id)
    assert code == 201

    # Тренеру — о записи, клиенту — два напоминания по умолчанию, тренеру напоминаний нет
    assert await queue(session) == [
        (ADMIN_TELEGRAM_ID, "new_booking", "", "pending"),
        (CLIENT_TG, "reminder", "client", "pending"),
        (CLIENT_TG, "reminder", "client", "pending"),
    ]
    assert await reminder_times(session) == [START - timedelta(days=1), START - timedelta(hours=2)]

    channel = FakeChannel()
    assert await dispatch(channel, datetime.now(UTC)) == 1
    assert channel.sent == [
        (ADMIN_TELEGRAM_ID, "🆕 Новая запись\nИван\nПерсональная · пн, 7 янв, 10:00")
    ]


async def test_confirm_decline_cancel(client: AsyncClient, session: AsyncSession) -> None:
    trainer_headers, trainer_id, service_id = await setup_trainer(client)
    await client.patch("/api/trainer/me", headers=trainer_headers, json={"auto_confirm": False})
    headers = await new_client(client, session, trainer_id, CLIENT_TG)
    _, first = await book(client, headers, trainer_id, service_id)
    _, second = await book(client, headers, trainer_id, service_id, ELEVEN)

    channel = FakeChannel()
    await dispatch(channel, datetime.now(UTC))
    assert [text.splitlines()[0] for _, text in channel.sent] == [
        "🆕 Новая запись, ждёт подтверждения",
        "🆕 Новая запись, ждёт подтверждения",
    ]
    # Пока запись не подтверждена, напоминаний нет
    assert await reminder_times(session) == []

    await client.post(f"/api/trainer/bookings/{first['id']}/confirm", headers=trainer_headers)
    await client.post(f"/api/trainer/bookings/{second['id']}/decline", headers=trainer_headers)
    assert len(await reminder_times(session)) == 2
    channel.sent.clear()
    await dispatch(channel, datetime.now(UTC))
    assert channel.sent == [
        (CLIENT_TG, "✅ Тренер Иван подтвердил запись\nПерсональная · пн, 7 янв, 10:00"),
        (
            CLIENT_TG,
            "Тренер Иван не сможет провести занятие в это время\n"
            "Персональная · пн, 7 янв, 11:00\nВыберите другое окошко в приложении.",
        ),
    ]

    # Клиент отменяет подтверждённую запись: тренер узнаёт, напоминания исчезают
    response = await client.post(f"/api/client/bookings/{first['id']}/cancel", headers=headers)
    assert response.status_code == 200, response.text
    assert await reminder_times(session) == []
    channel.sent.clear()
    await dispatch(channel, datetime.now(UTC))
    assert channel.sent == [
        (ADMIN_TELEGRAM_ID, "❌ Иван отменил(а) запись\nПерсональная · пн, 7 янв, 10:00")
    ]


async def test_trainer_books_and_cancels(client: AsyncClient, session: AsyncSession) -> None:
    trainer_headers, trainer_id, service_id = await setup_trainer(client)
    headers = await new_client(client, session, trainer_id, CLIENT_TG)
    client_id = (await client.get("/api/me", headers=headers)).json()["id"]
    response = await client.post(
        "/api/trainer/bookings",
        headers=trainer_headers,
        json={"client_id": client_id, "service_id": service_id, "starts_at": TEN},
    )
    booking_id = response.json()["id"]
    await client.post(f"/api/trainer/bookings/{booking_id}/cancel", headers=trainer_headers)

    channel = FakeChannel()
    await dispatch(channel, datetime.now(UTC))
    # Запись уже отменена: сообщение «вас записали» не нужно, приходит только отмена
    assert channel.sent == [
        (CLIENT_TG, "❌ Тренер Иван отменил запись\nПерсональная · пн, 7 янв, 10:00")
    ]
    assert [row[3] for row in await queue(session)] == ["skipped", "sent"]


async def test_reminder_exactly_once(client: AsyncClient, session: AsyncSession) -> None:
    _, trainer_id, service_id = await setup_trainer(client)
    headers = await new_client(client, session, trainer_id, CLIENT_TG)
    await book(client, headers, trainer_id, service_id)
    await dispatch(FakeChannel(), datetime.now(UTC))

    # Два отправщика одновременно, как два контейнера: каждое сообщение уходит один раз
    day_before = START - timedelta(days=1) + timedelta(seconds=30)
    slow = FakeChannel(delay=0.2)
    counts = await asyncio.gather(dispatch(slow, day_before), dispatch(slow, day_before))
    assert sorted(counts) == [0, 1]
    assert slow.sent == [(CLIENT_TG, "⏰ Напоминание: завтра в 10:00 тренировка\n"
                                     "Персональная, тренер Иван")]  # fmt: skip

    # «Перезапуск»: новый отправщик ничего не шлёт повторно
    again = FakeChannel()
    assert await Sender(get_sessionmaker(), again, lambda: day_before).run() == 0
    assert again.sent == []

    # Процесс упал посреди отправки: блокировка держится, пока транзакция жива,
    # и снимается вместе с ней. Следующий проход отправляет напоминание
    two_hours = START - timedelta(hours=2)
    async with get_sessionmaker()() as crashed:
        await crashed.execute(
            select(Notification).where(Notification.status == "pending").with_for_update()
        )
        assert await dispatch(again, two_hours) == 0
        await crashed.rollback()
    assert await dispatch(again, two_hours) == 1
    assert again.sent == [(CLIENT_TG, "⏰ Напоминание: сегодня в 10:00 тренировка\n"
                                      "Персональная, тренер Иван")]  # fmt: skip
    assert await dispatch(again, two_hours) == 0


async def test_stale_reminders(client: AsyncClient, session: AsyncSession) -> None:
    _, trainer_id, service_id = await setup_trainer(client)
    headers = await new_client(client, session, trainer_id, CLIENT_TG)
    await book(client, headers, trainer_id, service_id)
    await book(client, headers, trainer_id, service_id, ELEVEN)
    channel = FakeChannel()
    await dispatch(channel, datetime.now(UTC))
    channel.sent.clear()

    # Сервис лежал больше суток: о 10:00 уже поздно, об 11:00 — одно напоминание вместо двух
    await dispatch(channel, START + timedelta(minutes=5))
    assert channel.sent == [(CLIENT_TG, "⏰ Напоминание: сегодня в 11:00 тренировка\n"
                                        "Персональная, тренер Иван")]  # fmt: skip
    assert [row[3] for row in await queue(session)] == [
        "sent", "sent", "skipped", "skipped", "skipped", "sent",
    ]  # fmt: skip


async def test_delivery_errors(client: AsyncClient, session: AsyncSession) -> None:
    _, trainer_id, service_id = await setup_trainer(client)
    headers = await new_client(client, session, trainer_id, CLIENT_TG)
    await book(client, headers, trainer_id, service_id)
    now = datetime.now(UTC)

    # Сбой сети: попробуем позже
    assert await dispatch(FakeChannel(error=DeliveryError("timeout", permanent=False)), now) == 1
    row = await session.scalar(
        select(Notification)
        .where(Notification.kind == "new_booking")
        .execution_options(populate_existing=True)
    )
    assert row is not None
    assert (row.status, row.attempts, row.error) == ("pending", 1, "timeout")
    assert row.send_at > now + timedelta(minutes=1)
    assert await dispatch(FakeChannel(), now) == 0

    # Тренер заблокировал бота: больше не пытаемся
    blocked = DeliveryError("Forbidden: bot was blocked by the user", permanent=True)
    assert await dispatch(FakeChannel(error=blocked), now + timedelta(minutes=5)) == 1
    await session.refresh(row)
    assert (row.status, row.attempts) == ("failed", 2)


async def test_reminder_settings(client: AsyncClient, session: AsyncSession) -> None:
    trainer_headers, trainer_id, service_id = await setup_trainer(client)
    headers = await new_client(client, session, trainer_id, CLIENT_TG)
    await book(client, headers, trainer_id, service_id)

    mine = (await client.get("/api/me/reminders", headers=headers)).json()
    assert mine == {
        "client": {"enabled": True, "offsets": [1440, 120], "attendance_prompt": True},
        "trainer": None,
    }
    forbidden = await client.put(
        "/api/me/reminders/trainer",
        headers=headers,
        json={"enabled": True, "offsets": [60]},
    )
    assert forbidden.status_code == 403
    bad = await client.put(
        "/api/me/reminders/client", headers=headers, json={"enabled": True, "offsets": [1]}
    )
    assert bad.status_code == 422

    # Смена настроек пересчитывает напоминания о будущих записях
    saved = await client.put(
        "/api/me/reminders/client",
        headers=headers,
        json={"enabled": True, "offsets": [30, 180, 30]},
    )
    assert saved.json() == {"enabled": True, "offsets": [180, 30], "attendance_prompt": True}
    assert await reminder_times(session) == [
        START - timedelta(hours=3),
        START - timedelta(minutes=30),
    ]
    await client.put(
        "/api/me/reminders/client", headers=headers, json={"enabled": False, "offsets": [180]}
    )
    assert await reminder_times(session) == []

    # Тренер включает напоминания себе
    theirs = (await client.get("/api/me/reminders", headers=trainer_headers)).json()
    assert theirs["trainer"] == {"enabled": False, "offsets": [60], "attendance_prompt": True}
    await client.put(
        "/api/me/reminders/trainer",
        headers=trainer_headers,
        json={"enabled": True, "offsets": [60], "attendance_prompt": False},
    )
    assert await reminder_times(session) == [START - timedelta(hours=1)]
    channel = FakeChannel()
    await dispatch(channel, START - timedelta(minutes=59))
    assert (ADMIN_TELEGRAM_ID, "⏰ Сегодня в 10:00: Иван\nПерсональная") in channel.sent

    # Отправленное напоминание не повторится, даже если настройки сохранить ещё раз
    await client.put(
        "/api/me/reminders/trainer",
        headers=trainer_headers,
        json={"enabled": True, "offsets": [60]},
    )
    assert await reminder_times(session) == []


async def test_kick_sends_right_away(client: AsyncClient, session: AsyncSession) -> None:
    _, trainer_id, service_id = await setup_trainer(client)
    headers = await new_client(client, session, trainer_id, CLIENT_TG)
    channel = FakeChannel()
    sender = Sender(get_sessionmaker(), channel)
    sender.register()
    try:
        await book(client, headers, trainer_id, service_id)
        for _ in range(50):
            if channel.sent:
                break
            await asyncio.sleep(0.05)
    finally:
        sender.unregister()
    assert [tg for tg, _ in channel.sent] == [ADMIN_TELEGRAM_ID]
