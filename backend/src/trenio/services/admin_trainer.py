"""Профиль тренера в админке: всё о тренере на одной странице.

Как и в списке, админ видит настройки и количества, но не деньги клиентов у тренера:
цен услуг здесь нет, только оплаты самого тренера за Pro.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from trenio.db.models import (
    AdminAuditEntry,
    PromoRedemption,
    ScheduleRule,
    Service,
    SubscriptionPayment,
    SupportTicket,
    Trainer,
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
        TrainerRef(trainer_id, name)
        for trainer_id, name in (
            await session.execute(
                select(Trainer.id, Trainer.display_name)
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
        referrals=referrals,
    )
