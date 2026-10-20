"""Деньги Trenio в админке: MRR, прогноз, продления и оплаты с ботом-источником."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import ADMIN_TELEGRAM_ID
from tests.factories import make_init_data
from tests.test_api import login
from tests.test_referrals import make_trainer
from trenio.db.models import SubscriptionPayment, Trainer
from trenio.services import admin_stats, saas_money
from trenio.services.saas_money import Risk


async def _paid(session: AsyncSession, trainer: Trainer, at: datetime, amount: int = 349) -> None:
    session.add(
        SubscriptionPayment(
            trainer_id=trainer.id,
            plan="month",
            days=30,
            price=349,
            amount=amount,
            status="paid",
            paid_at=at,
        )
    )


async def test_mrr_forecast_and_payments(session: AsyncSession) -> None:
    now = datetime.now(UTC)
    anna = await make_trainer(session, 7, "Анна")
    boris = await make_trainer(session, 8, "Борис")
    vera = await make_trainer(session, 9, "Вера")
    # Анна оплатила и продлится только через полтора месяца, Борис — на этой неделе,
    # Вера ещё на пробном периоде, который скоро кончится
    anna.trial_until = now - timedelta(days=5)
    anna.pro_until = now + timedelta(days=50)
    boris.trial_until = now - timedelta(days=20)
    boris.pro_until = now + timedelta(days=3)
    vera.trial_until = now + timedelta(days=2)
    await _paid(session, anna, now - timedelta(days=5))
    # Часть цены Бориса покрыл баланс: пришло деньгами 300
    await _paid(session, boris, now - timedelta(days=27), amount=300)
    await session.commit()

    rows = await admin_stats.trainer_rows(session, now)
    data = await saas_money.summary(session, now, rows, admin_trainer_ids=set())
    assert (data.mrr, data.paying, data.trials, data.arpu) == (698, 2, 1, 349)
    assert data.trial_conversion == 100
    assert data.received_total == 649
    assert sum(m.received for m in data.months) == 649

    assert [(r.name, r.kind) for r in data.renewals] == [("Вера", "trial"), ("Борис", "pro")]
    # Ни у кого нет расписания: продления под средним риском, в осторожный прогноз не идут
    assert {r.risk for r in data.renewals} == {Risk.MEDIUM}
    assert data.forecast.optimistic == 349 * 3
    assert data.forecast.realistic == 349 * 3
    assert data.forecast.cautious == 349

    assert [(p.name, p.bot) for p in data.payments] == [("Анна", None), ("Борис", None)]


async def test_admins_are_not_counted(session: AsyncSession) -> None:
    now = datetime.now(UTC)
    admin = await make_trainer(session, 7, "Тихон")
    admin.pro_until = now + timedelta(days=10)
    await session.commit()
    rows = await admin_stats.trainer_rows(session, now)
    data = await saas_money.summary(session, now, rows, admin_trainer_ids={admin.id})
    assert (data.mrr, data.paying, data.renewals) == (0, 0, [])


async def test_money_endpoint(client: AsyncClient) -> None:
    token = await login(client, make_init_data(user_id=ADMIN_TELEGRAM_ID))
    response = await client.get("/api/admin/money", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mrr"] == 0 and len(body["months"]) == saas_money.HISTORY_MONTHS
