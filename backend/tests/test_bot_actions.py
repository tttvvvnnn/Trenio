"""Кнопки под уведомлениями и уведомления о блоках."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import ADMIN_TELEGRAM_ID
from tests.test_bookings import ELEVEN, TEN, book, new_client, setup_trainer
from tests.test_notifications import CLIENT_TG, START, FakeChannel, dispatch
from tests.test_packages import TEN_FOR_20K, client_id_of, mark, past_booking
from trenio.bot.actions import apply_action
from trenio.bot.callbacks import Action, BookingAction
from trenio.db.models import Booking, Notification
from trenio.delivery.channel import OutMessage

STRANGER_TG = 7007


def callbacks(message: OutMessage) -> list[str | None]:
    return [button.callback_data for row in message.buttons for button in row]


async def press(
    session: AsyncSession, telegram_id: int, action: Action, booking_id: object, now: datetime
) -> tuple[bool, str]:
    outcome = await apply_action(
        session, telegram_id, BookingAction(action=action, booking_id=int(str(booking_id))), now
    )
    return outcome.ok, outcome.text


async def test_confirm_and_decline_buttons(client: AsyncClient, session: AsyncSession) -> None:
    trainer_headers, trainer_id, service_id = await setup_trainer(client)
    await client.patch("/api/trainer/me", headers=trainer_headers, json={"auto_confirm": False})
    headers = await new_client(client, session, trainer_id, CLIENT_TG)
    await new_client(client, session, trainer_id, STRANGER_TG)
    _, first = await book(client, headers, trainer_id, service_id)
    _, second = await book(client, headers, trainer_id, service_id, ELEVEN)

    channel = FakeChannel()
    now = datetime.now(UTC)
    await dispatch(channel, now)
    assert callbacks(channel.messages[0]) == [
        f"bk:confirm:{first['id']}",
        f"bk:decline:{first['id']}",
    ]

    # Чужой человек не подтвердит запись, даже подделав кнопку
    assert await press(session, STRANGER_TG, Action.CONFIRM, first["id"], now) == (
        False,
        "Запись не найдена.",
    )
    assert await press(session, ADMIN_TELEGRAM_ID, Action.CONFIRM, first["id"], now) == (
        True,
        "✓ Подтверждено",
    )
    assert await press(session, ADMIN_TELEGRAM_ID, Action.DECLINE, first["id"], now) == (
        False,
        "Запись уже отменена или изменена в приложении.",
    )
    assert await press(session, ADMIN_TELEGRAM_ID, Action.DECLINE, second["id"], now) == (
        True,
        "✗ Отклонено",
    )

    channel.sent.clear()
    await dispatch(channel, now)
    assert [text.splitlines()[0] for _, text in channel.sent] == [
        "✅ Тренер Иван подтвердил запись",
        "Тренер Иван не сможет провести занятие в это время",
    ]


async def test_client_cancel_button(client: AsyncClient, session: AsyncSession) -> None:
    trainer_headers, trainer_id, service_id = await setup_trainer(client)
    headers = await new_client(client, session, trainer_id, CLIENT_TG)
    await new_client(client, session, trainer_id, STRANGER_TG)
    response = await client.post(
        "/api/trainer/bookings",
        headers=trainer_headers,
        json={
            "client_id": await client_id_of(client, headers),
            "service_id": service_id,
            "starts_at": TEN,
        },
    )
    booking_id = response.json()["id"]

    channel = FakeChannel()
    now = datetime.now(UTC)
    await dispatch(channel, now)
    assert callbacks(channel.messages[0])[0] == f"bk:cancel:{booking_id}"

    # Напоминание за 2 часа: отменять поздно (срок отмены тренера 12 ч), кнопки нет
    await dispatch(channel, START - timedelta(days=1))
    assert callbacks(channel.messages[-1]) == [f"bk:cancel:{booking_id}"]
    late = START - timedelta(hours=2)
    assert await press(session, CLIENT_TG, Action.CANCEL, booking_id, late) == (
        False,
        "Отменить самому уже поздно. Напишите тренеру.",
    )
    assert await press(session, STRANGER_TG, Action.CANCEL, booking_id, now) == (
        False,
        "Запись не найдена.",
    )
    assert await press(session, CLIENT_TG, Action.CANCEL, booking_id, now) == (
        True,
        "✗ Запись отменена",
    )
    channel.sent.clear()
    await dispatch(channel, late)
    # Тренеру — об отмене; напоминание за 2 часа и просьба отметить занятие исчезли
    assert [tg for tg, _ in channel.sent] == [ADMIN_TELEGRAM_ID]
    assert "отменил(а) запись" in channel.sent[0][1]


async def test_attendance_prompt(client: AsyncClient, session: AsyncSession) -> None:
    _, trainer_id, service_id = await setup_trainer(client)
    headers = await new_client(client, session, trainer_id, CLIENT_TG)
    _, first = await book(client, headers, trainer_id, service_id)
    _, second = await book(client, headers, trainer_id, service_id, ELEVEN)
    channel = FakeChannel()
    await dispatch(channel, datetime.now(UTC))

    # Вторую запись тренер отметил в приложении до конца занятия: просьба не нужна
    after_second = START + timedelta(hours=2, minutes=1)
    assert await press(
        session, ADMIN_TELEGRAM_ID, Action.MISSED_FREE, second["id"], START + timedelta(hours=1)
    ) == (True, "✓ Отмечено: пропуск, не списано")

    channel = FakeChannel()
    await dispatch(channel, after_second)
    prompts = [m for m in channel.messages if m.text.startswith("Как прошло")]
    assert [m.text for m in prompts] == [
        "Как прошло занятие?\nИван, Персональная · пн, 7 янв, 10:00"
    ]
    assert callbacks(prompts[0]) == [
        f"bk:attended:{first['id']}",
        f"bk:missed_charged:{first['id']}",
        f"bk:missed_free:{first['id']}",
    ]
    assert await press(session, ADMIN_TELEGRAM_ID, Action.ATTENDED, first["id"], after_second) == (
        True,
        "✓ Отмечено: прошла",
    )
    booking = await session.get(Booking, first["id"], populate_existing=True)
    assert booking is not None and booking.attendance == "attended"


async def test_attendance_prompt_setting(client: AsyncClient, session: AsyncSession) -> None:
    trainer_headers, trainer_id, service_id = await setup_trainer(client)
    headers = await new_client(client, session, trainer_id, CLIENT_TG)
    await book(client, headers, trainer_id, service_id)

    async def prompts() -> int:
        rows = await session.scalars(
            select(Notification.id).where(
                Notification.kind == "attendance_prompt", Notification.status == "pending"
            )
        )
        return len(rows.all())

    assert await prompts() == 1
    await client.put(
        "/api/me/reminders/trainer",
        headers=trainer_headers,
        json={"enabled": False, "offsets": [60], "attendance_prompt": False},
    )
    assert await prompts() == 0
    await client.put(
        "/api/me/reminders/trainer",
        headers=trainer_headers,
        json={"enabled": False, "offsets": [60], "attendance_prompt": True},
    )
    assert await prompts() == 1


async def test_package_ending(client: AsyncClient, session: AsyncSession) -> None:
    trainer_headers, trainer_id, service_id = await setup_trainer(client)
    headers = await new_client(client, session, trainer_id, CLIENT_TG)
    client_id = await client_id_of(client, headers)
    response = await client.post(
        f"/api/trainer/clients/{client_id}/packages",
        headers=trainer_headers,
        json={**TEN_FOR_20K, "sessions_count": 3},
    )
    package_id = response.json()["id"]
    await client.post(
        f"/api/trainer/packages/{package_id}/payments",
        headers=trainer_headers,
        json={"amount": 15000},
    )
    done = [await past_booking(session, trainer_id, client_id, service_id, d) for d in (3, 2, 1)]

    channel = FakeChannel()
    assert (await mark(client, trainer_headers, done[0], "attended"))[0] == 200
    await dispatch(channel, datetime.now(UTC))
    assert channel.sent == [
        (CLIENT_TG, "📦 В блоке «10 персональных» осталось 2 занятия\n"
                    "Осталось доплатить 5 000 ₽"),
        (ADMIN_TELEGRAM_ID, "📦 У клиента Иван в блоке «10 персональных» осталось 2 занятия\n"
                            "Долг по блоку: 5 000 ₽"),
    ]  # fmt: skip

    # Снять и поставить отметку снова: повторного предупреждения нет
    await mark(client, trainer_headers, done[0], None)
    await mark(client, trainer_headers, done[0], "attended")
    await mark(client, trainer_headers, done[1], "missed_charged")
    channel.sent.clear()
    await dispatch(channel, datetime.now(UTC))
    assert [text.splitlines()[0] for _, text in channel.sent] == [
        "📦 В блоке «10 персональных» осталось 1 занятие",
        "📦 У клиента Иван в блоке «10 персональных» осталось 1 занятие",
    ]

    await mark(client, trainer_headers, done[2], "attended")
    # Отметку сняли раньше, чем ушло сообщение: устаревшее «закончился» не отправляем
    await mark(client, trainer_headers, done[2], None)
    channel.sent.clear()
    await dispatch(channel, datetime.now(UTC))
    assert channel.sent == []

    await mark(client, trainer_headers, done[2], "missed_free")
    await mark(client, trainer_headers, done[2], "attended")
    await dispatch(channel, datetime.now(UTC))
    assert [text.splitlines()[0] for _, text in channel.sent] == [
        "📦 Блок «10 персональных» закончился. Договоритесь с тренером о новом",
        "📦 У клиента Иван закончился блок «10 персональных»",
    ]
