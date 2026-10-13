"""Блоки тренировок: шаблоны, купленные блоки, платежи и списание занятий.

Занятие списывается только отметкой тренера: «прошла» или «пропуск, списать».
Отмена и неявка сами ничего не списывают. Списание идёт из самого старого подходящего
блока: та же услуга или «любая», блок не закрыт, действует на дату занятия и в нём есть
свободные занятия. Если такого блока нет, занятие считается разовым.

Отметки одного клиента идут под блокировкой его блоков у этого тренера (FOR UPDATE),
поэтому два быстрых нажатия не спишут из блока больше занятий, чем в нём есть.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.db.models import (
    ACTIVE_BOOKING_STATUSES,
    Booking,
    Package,
    PackageSession,
    PackageTemplate,
    Payment,
    Service,
    Trainer,
    TrainerClient,
)
from trenio.delivery.kick import kick
from trenio.services import notifications
from trenio.services.bookings import BookingStatus
from trenio.services.clients import is_client

# Сколько оставшихся занятий считается «блок заканчивается, предложите новый»
ENDING_SOON_LEFT = 2


class Attendance(StrEnum):
    ATTENDED = "attended"
    MISSED_CHARGED = "missed_charged"
    MISSED_FREE = "missed_free"


# Отметки, которые списывают занятие из блока
CHARGED = frozenset({Attendance.ATTENDED.value, Attendance.MISSED_CHARGED.value})


class PackageStatus(StrEnum):
    ACTIVE = "active"
    # Все занятия списаны
    FINISHED = "finished"
    # Срок действия вышел, а занятия остались
    EXPIRED = "expired"
    # Тренер закрыл досрочно
    CLOSED = "closed"


class PackageError(StrEnum):
    NOT_FOUND = "not_found"
    NOT_CLIENT = "not_client"
    SERVICE_NOT_FOUND = "service_not_found"
    # Отмечать посещение можно только после начала занятия
    NOT_STARTED = "not_started"
    # Отметка не подходит к записи: например, «прошла» у отменённой
    WRONG_STATUS = "wrong_status"
    NO_SESSIONS_LEFT = "no_sessions_left"
    PACKAGE_CLOSED = "package_closed"
    # Занятий в блоке не может стать меньше, чем уже списано
    COUNT_BELOW_USED = "count_below_used"
    # Блок со списанными занятиями не удаляем, его можно закрыть
    HAS_SESSIONS = "has_sessions"
    # Занятие, списанное за запись, снимается отметкой в самой записи
    LINKED_TO_BOOKING = "linked_to_booking"
    BAD_DATES = "bad_dates"


class PackageRejected(Exception):
    def __init__(self, reason: PackageError) -> None:
        super().__init__(reason)
        self.reason = reason


# --- Подсчёты по блоку ---


def used(package: Package) -> int:
    return len(package.sessions)


def left(package: Package) -> int:
    return max(package.sessions_count - used(package), 0)


def paid(package: Package) -> int:
    return sum(payment.amount for payment in package.payments)


def due(package: Package) -> int:
    """Сколько осталось доплатить. Переплата долгом не считается."""
    return max(package.price - paid(package), 0)


def status(package: Package, today: date) -> PackageStatus:
    if package.closed_at is not None:
        return PackageStatus.CLOSED
    if left(package) == 0:
        return PackageStatus.FINISHED
    if package.valid_until is not None and package.valid_until < today:
        return PackageStatus.EXPIRED
    return PackageStatus.ACTIVE


def ending_soon(package: Package, today: date) -> bool:
    return status(package, today) is PackageStatus.ACTIVE and left(package) <= ENDING_SOON_LEFT


def can_charge(package: Package, service_id: int, day: date) -> bool:
    """Можно ли списать из блока занятие этой услуги в этот день."""
    return (
        package.closed_at is None
        and (package.service_id is None or package.service_id == service_id)
        and (package.valid_until is None or package.valid_until >= day)
        and left(package) > 0
    )


def trainer_today(trainer: Trainer, now: datetime) -> date:
    return now.astimezone(ZoneInfo(trainer.timezone)).date()


def booking_day(booking: Booking) -> date:
    """День занятия по часовому поясу тренера."""
    return booking.starts_at.astimezone(ZoneInfo(booking.trainer.timezone)).date()


# --- Шаблоны ---


@dataclass(frozen=True)
class TemplateData:
    name: str
    service_id: int | None
    sessions_count: int
    price: int
    valid_days: int | None


async def _check_service(session: AsyncSession, trainer: Trainer, service_id: int | None) -> None:
    if service_id is None:
        return
    found = await session.scalar(
        select(Service.id).where(Service.id == service_id, Service.trainer_id == trainer.id)
    )
    if found is None:
        raise PackageRejected(PackageError.SERVICE_NOT_FOUND)


async def list_templates(session: AsyncSession, trainer: Trainer) -> Sequence[PackageTemplate]:
    stmt = (
        select(PackageTemplate)
        .where(PackageTemplate.trainer_id == trainer.id)
        .order_by(PackageTemplate.sessions_count, PackageTemplate.id)
    )
    return (await session.scalars(stmt)).all()


async def _get_template(
    session: AsyncSession, trainer: Trainer, template_id: int
) -> PackageTemplate:
    template = await session.scalar(
        select(PackageTemplate).where(
            PackageTemplate.id == template_id, PackageTemplate.trainer_id == trainer.id
        )
    )
    if template is None:
        raise PackageRejected(PackageError.NOT_FOUND)
    return template


async def create_template(
    session: AsyncSession, trainer: Trainer, data: TemplateData
) -> PackageTemplate:
    await _check_service(session, trainer, data.service_id)
    template = PackageTemplate(
        trainer_id=trainer.id,
        name=data.name,
        service_id=data.service_id,
        sessions_count=data.sessions_count,
        price=data.price,
        valid_days=data.valid_days,
    )
    session.add(template)
    await session.commit()
    return await _get_template(session, trainer, template.id)


async def replace_template(
    session: AsyncSession, trainer: Trainer, template_id: int, data: TemplateData
) -> PackageTemplate:
    template = await _get_template(session, trainer, template_id)
    await _check_service(session, trainer, data.service_id)
    template.name = data.name
    template.service_id = data.service_id
    template.sessions_count = data.sessions_count
    template.price = data.price
    template.valid_days = data.valid_days
    await session.commit()
    # populate_existing: подтянуть новую услугу вместо закешированной
    found = await session.scalar(
        select(PackageTemplate)
        .where(PackageTemplate.id == template_id)
        .execution_options(populate_existing=True)
    )
    assert found is not None
    return found


async def delete_template(session: AsyncSession, trainer: Trainer, template_id: int) -> None:
    # Блоки копируют поля шаблона, поэтому шаблон можно удалить без последствий
    template = await _get_template(session, trainer, template_id)
    await session.delete(template)
    await session.commit()


# --- Блоки ---


async def _load_packages(
    session: AsyncSession, *conditions: ColumnElement[bool]
) -> Sequence[Package]:
    # populate_existing: списания и платежи могли поменяться в этой же сессии
    stmt = (
        select(Package)
        .where(*conditions)
        .order_by(Package.purchased_on, Package.id)
        .execution_options(populate_existing=True)
    )
    return (await session.scalars(stmt)).all()


async def list_client_packages(
    session: AsyncSession, trainer: Trainer, client_id: int
) -> Sequence[Package]:
    return await _load_packages(
        session, Package.trainer_id == trainer.id, Package.client_id == client_id
    )


async def list_trainer_packages(session: AsyncSession, trainer: Trainer) -> Sequence[Package]:
    return await _load_packages(session, Package.trainer_id == trainer.id)


async def list_my_packages(session: AsyncSession, client_id: int) -> Sequence[Package]:
    """Блоки клиента у всех тренеров."""
    return await _load_packages(session, Package.client_id == client_id)


async def get_package(session: AsyncSession, trainer: Trainer, package_id: int) -> Package:
    found = await _load_packages(
        session, Package.id == package_id, Package.trainer_id == trainer.id
    )
    if not found:
        raise PackageRejected(PackageError.NOT_FOUND)
    return found[0]


async def _lock_package(session: AsyncSession, package: Package) -> Package:
    await session.execute(select(Package.id).where(Package.id == package.id).with_for_update())
    found = await _load_packages(session, Package.id == package.id)
    return found[0]


@dataclass(frozen=True)
class PackageData:
    name: str
    service_id: int | None
    sessions_count: int
    price: int
    purchased_on: date
    valid_until: date | None


async def create_package(
    session: AsyncSession, trainer: Trainer, client_id: int, data: PackageData
) -> Package:
    """Тренер продаёт клиенту блок."""
    if not await is_client(session, trainer, client_id):
        raise PackageRejected(PackageError.NOT_CLIENT)
    await _check_service(session, trainer, data.service_id)
    if data.valid_until is not None and data.valid_until < data.purchased_on:
        raise PackageRejected(PackageError.BAD_DATES)
    package = Package(
        trainer_id=trainer.id,
        client_id=client_id,
        name=data.name,
        service_id=data.service_id,
        sessions_count=data.sessions_count,
        price=data.price,
        purchased_on=data.purchased_on,
        valid_until=data.valid_until,
    )
    session.add(package)
    await session.commit()
    return await get_package(session, trainer, package.id)


@dataclass(frozen=True)
class PackageChanges:
    name: str | None = None
    sessions_count: int | None = None
    price: int | None = None
    purchased_on: date | None = None
    valid_until: date | None = None
    clear_valid_until: bool = False
    closed: bool | None = None


async def update_package(
    session: AsyncSession, trainer: Trainer, package_id: int, changes: PackageChanges, now: datetime
) -> Package:
    package = await _lock_package(session, await get_package(session, trainer, package_id))
    if changes.sessions_count is not None and changes.sessions_count < used(package):
        await session.rollback()
        raise PackageRejected(PackageError.COUNT_BELOW_USED)
    if changes.name is not None:
        package.name = changes.name
    if changes.sessions_count is not None:
        package.sessions_count = changes.sessions_count
    if changes.price is not None:
        package.price = changes.price
    if changes.purchased_on is not None:
        package.purchased_on = changes.purchased_on
    if changes.clear_valid_until:
        package.valid_until = None
    elif changes.valid_until is not None:
        package.valid_until = changes.valid_until
    if package.valid_until is not None and package.valid_until < package.purchased_on:
        await session.rollback()
        raise PackageRejected(PackageError.BAD_DATES)
    if changes.closed is not None:
        package.closed_at = (package.closed_at or now) if changes.closed else None
    await session.commit()
    return await get_package(session, trainer, package_id)


async def delete_package(session: AsyncSession, trainer: Trainer, package_id: int) -> None:
    """Удалить блок, проданный по ошибке. Если занятия уже списаны, блок можно только закрыть."""
    package = await _lock_package(session, await get_package(session, trainer, package_id))
    if package.sessions:
        await session.rollback()
        raise PackageRejected(PackageError.HAS_SESSIONS)
    await session.delete(package)
    await session.commit()


async def add_payment(
    session: AsyncSession,
    trainer: Trainer,
    package_id: int,
    amount: int,
    paid_on: date,
    comment: str | None,
) -> Package:
    package = await get_package(session, trainer, package_id)
    session.add(Payment(package_id=package.id, amount=amount, paid_on=paid_on, comment=comment))
    await session.commit()
    return await get_package(session, trainer, package_id)


async def delete_payment(
    session: AsyncSession, trainer: Trainer, package_id: int, payment_id: int
) -> Package:
    package = await get_package(session, trainer, package_id)
    payment = next((p for p in package.payments if p.id == payment_id), None)
    if payment is None:
        raise PackageRejected(PackageError.NOT_FOUND)
    await session.delete(payment)
    await session.commit()
    return await get_package(session, trainer, package_id)


async def add_manual_session(
    session: AsyncSession, trainer: Trainer, package_id: int, day: date, attendance: Attendance
) -> Package:
    """Отметить в блоке занятие, на которое не было записи в Trenio."""
    if attendance.value not in CHARGED:
        raise PackageRejected(PackageError.WRONG_STATUS)
    package = await _lock_package(session, await get_package(session, trainer, package_id))
    if package.closed_at is not None:
        await session.rollback()
        raise PackageRejected(PackageError.PACKAGE_CLOSED)
    if left(package) == 0:
        await session.rollback()
        raise PackageRejected(PackageError.NO_SESSIONS_LEFT)
    session.add(PackageSession(package_id=package.id, day=day, status=attendance.value))
    await notifications.package_left(session, package, left(package) - 1, datetime.now(UTC))
    await session.commit()
    kick()
    return await get_package(session, trainer, package_id)


async def update_manual_session(
    session: AsyncSession,
    trainer: Trainer,
    package_id: int,
    session_id: int,
    day: date,
    attendance: Attendance,
) -> Package:
    """Поменять дату или отметку занятия, списанного вручную."""
    if attendance.value not in CHARGED:
        raise PackageRejected(PackageError.WRONG_STATUS)
    package = await get_package(session, trainer, package_id)
    found = next((s for s in package.sessions if s.id == session_id), None)
    if found is None:
        raise PackageRejected(PackageError.NOT_FOUND)
    if found.booking_id is not None:
        raise PackageRejected(PackageError.LINKED_TO_BOOKING)
    found.day = day
    found.status = attendance.value
    await session.commit()
    return await get_package(session, trainer, package_id)


async def delete_manual_session(
    session: AsyncSession, trainer: Trainer, package_id: int, session_id: int
) -> Package:
    package = await get_package(session, trainer, package_id)
    found = next((s for s in package.sessions if s.id == session_id), None)
    if found is None:
        raise PackageRejected(PackageError.NOT_FOUND)
    if found.booking_id is not None:
        raise PackageRejected(PackageError.LINKED_TO_BOOKING)
    await session.delete(found)
    await session.commit()
    return await get_package(session, trainer, package_id)


# --- Отметки посещений ---


async def _pick_package(session: AsyncSession, booking: Booking) -> Package | None:
    """Самый старый блок, из которого можно списать это занятие."""
    day = booking_day(booking)
    candidates = await _load_packages(
        session,
        Package.trainer_id == booking.trainer_id,
        Package.client_id == booking.client_id,
        Package.closed_at.is_(None),
    )
    return next((p for p in candidates if can_charge(p, booking.service_id, day)), None)


async def mark_attendance(
    session: AsyncSession, booking: Booking, attendance: Attendance | None, now: datetime
) -> Booking:
    """Отметка тренера после занятия. None снимает отметку и возвращает занятие в блок."""
    if booking.starts_at > now:
        raise PackageRejected(PackageError.NOT_STARTED)
    if booking.status == BookingStatus.DECLINED:
        raise PackageRejected(PackageError.WRONG_STATUS)
    # Отменённая запись не могла пройти, но позднюю отмену тренер вправе списать как пропуск
    if booking.status == BookingStatus.CANCELLED and attendance is Attendance.ATTENDED:
        raise PackageRejected(PackageError.WRONG_STATUS)

    # Очередь отметок клиента у тренера: вторая транзакция ждёт здесь, пока первая не закоммитит
    await session.execute(
        select(Package.id)
        .where(Package.trainer_id == booking.trainer_id, Package.client_id == booking.client_id)
        .order_by(Package.id)
        .with_for_update()
    )
    existing = await session.scalar(
        select(PackageSession).where(PackageSession.booking_id == booking.id)
    )
    charged = attendance is not None and attendance.value in CHARGED
    if existing is not None and charged:
        # «Прошла» ↔ «пропуск, списать»: занятие остаётся в том же блоке
        assert attendance is not None
        existing.status = attendance.value
    else:
        if existing is not None:
            await session.delete(existing)
            await session.flush()
        if charged:
            assert attendance is not None
            package = await _pick_package(session, booking)
            if package is not None:
                session.add(
                    PackageSession(
                        package_id=package.id,
                        booking_id=booking.id,
                        day=booking_day(booking),
                        status=attendance.value,
                    )
                )
                await notifications.package_left(session, package, left(package) - 1, now)
    if attendance is not None and booking.status == BookingStatus.PENDING:
        # Тренер не успел подтвердить, но занятие состоялось или учтено
        booking.status = BookingStatus.CONFIRMED
    booking.attendance = attendance.value if attendance is not None else None
    booking.attendance_marked_at = now if attendance is not None else None
    await session.commit()
    kick()
    return booking


def number_of(package: Package, package_session: PackageSession) -> int:
    """Порядковый номер занятия в блоке, 1…N, по датам."""
    return next(i for i, s in enumerate(package.sessions, 1) if s.id == package_session.id)


@dataclass(frozen=True)
class Charge:
    """Из какого блока списана запись и каким по счёту занятием."""

    package: Package
    number: int


@dataclass(frozen=True)
class Billing:
    # Записи, которые нужно оплачивать отдельно от блоков
    one_off: set[int]
    # Отмеченные записи: из какого блока списаны
    charges: dict[int, Charge]
    # Неотмеченные активные записи: в какой блок лягут, если пройдут
    planned: dict[int, Charge]
    # Разовые записи клиентов, которые уже покупали блоки у тренера: блок кончился.
    # Клиентов, которые блоками не пользуются, этим не выделяем
    out_of_block: set[int]


def simulate(packages: Sequence[Package], bookings: Sequence[Booking]) -> dict[int, Charge | None]:
    """Раскладывает неотмеченные записи по блокам так, как их потом спишут отметки.

    Записи идут по времени, каждая берёт самый старый подходящий блок, где ещё есть место
    с учётом уже разложенных. None — блока не хватило, запись будет разовой.
    """
    taken = {p.id: used(p) for p in packages}
    result: dict[int, Charge | None] = {}
    for booking in sorted(bookings, key=lambda b: (b.starts_at, b.id)):
        day = booking_day(booking)
        target = next(
            (
                p
                for p in packages
                if p.trainer_id == booking.trainer_id
                and p.client_id == booking.client_id
                and p.closed_at is None
                and (p.service_id is None or p.service_id == booking.service_id)
                and (p.valid_until is None or p.valid_until >= day)
                and taken[p.id] < p.sessions_count
            ),
            None,
        )
        if target is None:
            result[booking.id] = None
        else:
            taken[target.id] += 1
            result[booking.id] = Charge(target, taken[target.id])
    return result


# Неотмеченные записи старше этого в прогноз не попадают
FORECAST_DAYS = 62


@dataclass(frozen=True)
class Forecast:
    bookings: Sequence[Booking]
    plan: dict[int, Charge | None]

    def planned_for(self, package: Package) -> list[tuple[Booking, int]]:
        """Записи, которые лягут в этот блок, с будущими номерами занятий."""
        result = []
        for booking in self.bookings:
            charge = self.plan.get(booking.id)
            if charge is not None and charge.package.id == package.id:
                result.append((booking, charge.number))
        return result

    def one_off_after(self, client_id: int, now: datetime) -> int:
        """Сколько будущих записей клиента не покрыто блоками."""
        return sum(
            1
            for b in self.bookings
            if b.client_id == client_id and b.starts_at > now and self.plan.get(b.id) is None
        )


async def forecast(
    session: AsyncSession, trainer_ids: Iterable[int], client_ids: Iterable[int] | None = None
) -> Forecast:
    """Прогноз списаний по неотмеченным активным записям клиентов у тренеров.

    Давно забытые неотмеченные записи не учитываем, иначе они вечно занимали бы места в блоках.
    """
    trainer_ids = set(trainer_ids)
    package_conditions = [Package.trainer_id.in_(trainer_ids), Package.closed_at.is_(None)]
    booking_conditions = [
        Booking.trainer_id.in_(trainer_ids),
        Booking.attendance.is_(None),
        Booking.status.in_(ACTIVE_BOOKING_STATUSES),
        Booking.starts_at >= datetime.now(UTC) - timedelta(days=FORECAST_DAYS),
    ]
    if client_ids is not None:
        client_ids = set(client_ids)
        package_conditions.append(Package.client_id.in_(client_ids))
        booking_conditions.append(Booking.client_id.in_(client_ids))
    packages = await _load_packages(session, *package_conditions)
    bookings = (
        await session.scalars(
            select(Booking).where(*booking_conditions).order_by(Booking.starts_at, Booking.id)
        )
    ).all()
    return Forecast(bookings, simulate(packages, bookings))


async def billing(session: AsyncSession, bookings: Iterable[Booking]) -> Billing:
    """Как записи соотносятся с блоками.

    Отмеченная со списанием запись разовая, если её не из чего было списать.
    Неотмеченная активная запись разовая, если по прогнозу ей не хватит блока:
    более ранние записи клиента займут оставшиеся занятия раньше неё.
    """
    bookings = list(bookings)
    charged = [b for b in bookings if b.attendance in CHARGED]
    unmarked = [b for b in bookings if b.attendance is None and b.status in ACTIVE_BOOKING_STATUSES]
    one_off: set[int] = set()
    charges: dict[int, Charge] = {}
    planned: dict[int, Charge] = {}
    if charged:
        linked = (
            await session.scalars(
                select(PackageSession).where(PackageSession.booking_id.in_([b.id for b in charged]))
            )
        ).all()
        packages = {
            p.id: p
            for p in await _load_packages(session, Package.id.in_({s.package_id for s in linked}))
        }
        for package_session in linked:
            package = packages[package_session.package_id]
            assert package_session.booking_id is not None
            charges[package_session.booking_id] = Charge(
                package, number_of(package, package_session)
            )
        one_off.update(b.id for b in charged if b.id not in charges)
    if unmarked:
        plan = (
            await forecast(
                session, {b.trainer_id for b in unmarked}, {b.client_id for b in unmarked}
            )
        ).plan
        for booking in unmarked:
            if booking.id not in plan:
                continue
            charge = plan[booking.id]
            if charge is None:
                one_off.add(booking.id)
            else:
                planned[booking.id] = charge
    out_of_block: set[int] = set()
    if one_off:
        flagged = [b for b in bookings if b.id in one_off]
        buyers = {
            (trainer_id, client_id)
            for trainer_id, client_id in (
                await session.execute(
                    select(Package.trainer_id, Package.client_id)
                    .where(
                        Package.trainer_id.in_({b.trainer_id for b in flagged}),
                        Package.client_id.in_({b.client_id for b in flagged}),
                    )
                    .distinct()
                )
            ).all()
        }
        out_of_block = {b.id for b in flagged if (b.trainer_id, b.client_id) in buyers}
    return Billing(one_off, charges, planned, out_of_block)


async def list_unmarked(
    session: AsyncSession, trainer: Trainer, since: datetime, now: datetime
) -> Sequence[Booking]:
    """Прошедшие занятия без отметки тренера, самые свежие первыми."""
    stmt = (
        select(Booking)
        .where(
            Booking.trainer_id == trainer.id,
            Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            Booking.attendance.is_(None),
            Booking.starts_at <= now,
            Booking.starts_at >= since,
        )
        .order_by(Booking.starts_at.desc(), Booking.id.desc())
    )
    return (await session.scalars(stmt)).all()


# --- Карточка клиента ---


async def get_client_link(session: AsyncSession, trainer: Trainer, client_id: int) -> TrainerClient:
    link = await session.scalar(
        select(TrainerClient).where(
            TrainerClient.trainer_id == trainer.id, TrainerClient.user_id == client_id
        )
    )
    if link is None:
        raise PackageRejected(PackageError.NOT_CLIENT)
    return link


async def set_notes(
    session: AsyncSession, trainer: Trainer, client_id: int, notes: str | None
) -> TrainerClient:
    link = await get_client_link(session, trainer, client_id)
    link.notes = notes
    await session.commit()
    return link


async def client_history(
    session: AsyncSession, trainer: Trainer, client_id: int, limit: int
) -> Sequence[Booking]:
    """Все записи клиента у тренера, новые первыми."""
    stmt = (
        select(Booking)
        .where(Booking.trainer_id == trainer.id, Booking.client_id == client_id)
        .order_by(Booking.starts_at.desc(), Booking.id.desc())
        .limit(limit)
    )
    return (await session.scalars(stmt)).all()


@dataclass(frozen=True)
class ClientSummary:
    # Сколько занятий осталось в действующих блоках; None — действующих блоков нет
    sessions_left: int | None
    # Сколько клиент должен доплатить по всем блокам
    debt: int
    has_packages: bool
    # Сколько будущих записей не покрыто блоками, если клиент вообще покупал блоки
    upcoming_one_off: int = 0


def summarize(
    packages: Iterable[Package],
    today: date,
    plan: Forecast | None = None,
    now: datetime | None = None,
) -> dict[int, ClientSummary]:
    """Сводка по блокам для списка клиентов: client_id → остаток занятий, долг, записи без блока."""
    by_client: dict[int, list[Package]] = {}
    for package in packages:
        by_client.setdefault(package.client_id, []).append(package)
    clients = set(by_client)
    if plan is not None:
        clients.update(b.client_id for b in plan.bookings)
    result = {}
    for client_id in clients:
        own = by_client.get(client_id, [])
        active = [p for p in own if status(p, today) is PackageStatus.ACTIVE]
        result[client_id] = ClientSummary(
            sessions_left=sum(left(p) for p in active) if active else None,
            debt=sum(due(p) for p in own if p.closed_at is None),
            has_packages=bool(own),
            # Без блоков клиент платит за каждое занятие: это не повод для подсказки
            upcoming_one_off=(
                plan.one_off_after(client_id, now)
                if own and plan is not None and now is not None
                else 0
            ),
        )
    return result
