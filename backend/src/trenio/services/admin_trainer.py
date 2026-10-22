"""Профиль тренера в админке: всё о тренере на одной странице.

Как и в списке, админ видит настройки и количества, но не деньги клиентов у тренера:
цен услуг здесь нет, только оплаты самого тренера за Pro.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.db.models import (
    AdminAuditEntry,
    Booking,
    Package,
    PromoRedemption,
    ScheduleRule,
    Service,
    SubscriptionPayment,
    SupportTicket,
    Trainer,
    TrainerClient,
    UserActivityDay,
)
from trenio.services.admin_clients import TrainerRef
from trenio.services.admin_stats import ADMIN_TIMEZONE

# Полоска активности в профиле, как в карточке клиента
ACTIVITY_DAYS = 30
PAYMENTS_LIMIT = 24
AUDIT_LIMIT = 30


@dataclass(frozen=True, slots=True)
class ServiceRow:
    name: str
    duration_min: int
    capacity: int
    is_active: bool


@dataclass(frozen=True, slots=True)
class HoursRow:
    # 0 — понедельник
    weekday: int
    start: time
    end: time


@dataclass(frozen=True, slots=True)
class Event:
    at: datetime
    # joined, onboarded, first_client, first_client_booking, first_package, paid, promo,
    # ticket, referral, trial_ended, pro_ended
    kind: str
    text: str
    # Другой тренер, о котором событие: пришёл по ссылке этого
    trainer_id: int | None = None


@dataclass(frozen=True, slots=True)
class Profile:
    activity: list[bool]
    services: list[ServiceRow]
    hours: list[HoursRow]
    payments: Sequence[SubscriptionPayment]
    # Сколько тренер заплатил деньгами и балансом за всё время
    paid_total: int
    promos: Sequence[PromoRedemption]
    tickets: Sequence[SupportTicket]
    audit: Sequence[AdminAuditEntry]
    referred_by: TrainerRef | None
    referrals: list[TrainerRef]
    # История тренера, свежие сверху. Действия админа — отдельно, в audit
    events: list[Event]


async def paid_totals(session: AsyncSession) -> dict[int, int]:
    """Сколько каждый тренер заплатил за Pro за всё время, вместе с балансом."""
    rows = await session.execute(
        select(SubscriptionPayment.trainer_id, func.sum(SubscriptionPayment.price))
        .where(SubscriptionPayment.status == "paid")
        .group_by(SubscriptionPayment.trainer_id)
    )
    return {int(trainer_id): int(total) for trainer_id, total in rows.all()}


TICKET_KIND = {"question": "вопрос", "problem": "проблема", "idea": "идея", "review": "отзыв"}
PROMO_KIND = {"percent": "−{}%", "rubles": "−{} ₽", "days": "{} дн. Pro"}


async def _first(session: AsyncSession, at: Any, *conditions: Any) -> datetime | None:
    return await session.scalar(select(func.min(at)).where(*conditions))


async def _events(
    session: AsyncSession,
    trainer: Trainer,
    now: datetime,
    payments: Sequence[SubscriptionPayment],
    promos: Sequence[PromoRedemption],
    tickets: Sequence[SupportTicket],
    referrals: list[tuple[TrainerRef, datetime]],
) -> list[Event]:
    events = [Event(trainer.created_at, "joined", "Получил доступ к Trenio")]
    if trainer.onboarded_at:
        events.append(Event(trainer.onboarded_at, "onboarded", "Прошёл первую настройку"))
    firsts = [
        (
            "first_client",
            "Первый клиент",
            await _first(session, TrainerClient.created_at, TrainerClient.trainer_id == trainer.id),
        ),
        (
            "first_client_booking",
            "Клиент впервые записался сам",
            await _first(
                session,
                Booking.created_at,
                Booking.trainer_id == trainer.id,
                Booking.created_by == "client",
            ),
        ),
        (
            "first_package",
            "Первый блок занятий",
            await _first(session, Package.created_at, Package.trainer_id == trainer.id),
        ),
    ]
    events += [Event(at, kind, text) for kind, text, at in firsts if at is not None]
    for payment in payments:
        if payment.status == "paid" and payment.paid_at:
            plan = "месяц" if payment.plan == "month" else payment.plan
            events.append(
                Event(payment.paid_at, "paid", f"Оплатил Pro ({plan}): {payment.price} ₽")
            )
    for promo in promos:
        value = PROMO_KIND.get(promo.code.kind, "{}").format(promo.code.value)
        events.append(
            Event(promo.created_at, "promo", f"Ввёл промокод {promo.code.code} ({value})")
        )
    for ticket in tickets:
        kind = TICKET_KIND.get(ticket.kind, ticket.kind)
        events.append(Event(ticket.created_at, "ticket", f"Написал в поддержку: {kind}"))
    for ref, at in referrals:
        events.append(Event(at, "referral", f"По его ссылке пришёл {ref.name}", ref.id))
    # Конец пробного и Pro — только прошедший и не перекрытый следующим сроком
    pro_until = trainer.pro_until
    trial_until = trainer.trial_until
    if trial_until and trial_until <= now and (pro_until is None or pro_until < trial_until):
        events.append(Event(trial_until, "trial_ended", "Закончился пробный период"))
    if pro_until and pro_until <= now:
        events.append(Event(pro_until, "pro_ended", "Закончился Pro"))
    events.sort(key=lambda e: e.at, reverse=True)
    return events


async def profile(session: AsyncSession, trainer: Trainer, now: datetime) -> Profile:
    today = now.astimezone(ADMIN_TIMEZONE).date()
    window = [today - timedelta(days=offset) for offset in range(ACTIVITY_DAYS - 1, -1, -1)]
    seen: set[date] = set(
        (
            await session.scalars(
                select(UserActivityDay.day).where(
                    UserActivityDay.user_id == trainer.user_id, UserActivityDay.day >= window[0]
                )
            )
        ).all()
    )
    services = [
        ServiceRow(s.name, s.duration_min, s.capacity, s.is_active)
        for s in (
            await session.scalars(
                select(Service)
                .where(Service.trainer_id == trainer.id)
                .order_by(Service.is_active.desc(), Service.id)
            )
        ).all()
    ]
    hours = [
        HoursRow(r.weekday, r.start_time, r.end_time)
        for r in (
            await session.scalars(
                select(ScheduleRule)
                .where(ScheduleRule.trainer_id == trainer.id)
                .order_by(ScheduleRule.weekday, ScheduleRule.start_time)
            )
        ).all()
    ]
    payments = (
        await session.scalars(
            select(SubscriptionPayment)
            .where(SubscriptionPayment.trainer_id == trainer.id)
            .order_by(SubscriptionPayment.created_at.desc(), SubscriptionPayment.id.desc())
            .limit(PAYMENTS_LIMIT)
        )
    ).all()
    paid_total = await session.scalar(
        select(func.coalesce(func.sum(SubscriptionPayment.price), 0)).where(
            SubscriptionPayment.trainer_id == trainer.id, SubscriptionPayment.status == "paid"
        )
    )
    promos = (
        await session.scalars(
            select(PromoRedemption)
            .where(PromoRedemption.trainer_id == trainer.id)
            .order_by(PromoRedemption.created_at.desc())
        )
    ).all()
    tickets = (
        await session.scalars(
            select(SupportTicket)
            .where(SupportTicket.trainer_id == trainer.id)
            .order_by(SupportTicket.created_at.desc(), SupportTicket.id.desc())
        )
    ).all()
    audit = (
        await session.scalars(
            select(AdminAuditEntry)
            .where(AdminAuditEntry.target == f"trainer:{trainer.id}")
            .order_by(AdminAuditEntry.id.desc())
            .limit(AUDIT_LIMIT)
        )
    ).all()
    referred_by = None
    if trainer.referred_by_id is not None:
        parent = await session.get(Trainer, trainer.referred_by_id)
        if parent is not None:
            referred_by = TrainerRef(parent.id, parent.display_name)
    referrals = [
        (TrainerRef(trainer_id, name), created_at)
        for trainer_id, name, created_at in (
            await session.execute(
                select(Trainer.id, Trainer.display_name, Trainer.created_at)
                .where(Trainer.referred_by_id == trainer.id)
                .order_by(Trainer.created_at)
            )
        ).all()
    ]
    return Profile(
        activity=[day in seen for day in window],
        services=services,
        hours=hours,
        payments=payments,
        paid_total=int(paid_total or 0),
        promos=promos,
        tickets=tickets,
        audit=audit,
        referred_by=referred_by,
        referrals=[ref for ref, _ in referrals],
        events=await _events(session, trainer, now, payments, promos, tickets, referrals),
    )
