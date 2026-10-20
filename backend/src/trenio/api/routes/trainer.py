from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from trenio.api.deps import CurrentTrainer, SessionDep
from trenio.bot.setup import get_bot_username
from trenio.config import get_settings
from trenio.db.models import Trainer
from trenio.services import avatars, billing, promo_codes, subscription
from trenio.services.trainers import (
    InvalidTimezone,
    TrainerProfileUpdate,
    list_referrals,
    referral_link,
    update_profile,
)

router = APIRouter(prefix="/trainer", tags=["trainer"])


class TrainerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    display_name: str
    timezone: str
    address: str | None
    auto_confirm: bool
    cancel_hours: int
    # Шаг времени начала записи в минутах; 0 — равен длительности услуги
    slot_step_min: int
    # Запись клиента без блока: allow — можно, confirm — с подтверждением, forbid — нельзя
    one_off_mode: str
    # Правила занятий, которые клиенты подтверждают перед записью
    rules: str | None
    rules_updated_at: datetime | None
    onboarded_at: datetime | None

    @classmethod
    def of(cls, trainer: Trainer) -> "TrainerOut":
        return cls.model_validate(trainer)


class TrainerProfileIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    timezone: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=256)
    auto_confirm: bool | None = None
    # Не больше недели: дальше правило отмены теряет смысл
    cancel_hours: int | None = Field(default=None, ge=0, le=168)
    slot_step_min: Literal[0, 5, 10, 15, 20, 30, 60] | None = None
    one_off_mode: Literal["allow", "confirm", "forbid"] | None = None
    rules: str | None = Field(default=None, max_length=4000)


@router.get("/me")
async def get_profile(trainer: CurrentTrainer) -> TrainerOut:
    return TrainerOut.of(trainer)


@router.patch("/me")
async def patch_profile(
    body: TrainerProfileIn, trainer: CurrentTrainer, session: SessionDep
) -> TrainerOut:
    """Онбординг и настройки тренера: первое сохранение отмечает онбординг пройденным."""
    changes = TrainerProfileUpdate(
        display_name=body.display_name.strip() if body.display_name else None,
        timezone=body.timezone,
        address=body.address.strip() if body.address is not None else None,
        auto_confirm=body.auto_confirm,
        cancel_hours=body.cancel_hours,
        slot_step_min=body.slot_step_min,
        one_off_mode=body.one_off_mode,
        rules=body.rules.strip() if body.rules is not None else None,
    )
    try:
        trainer = await update_profile(session, trainer, changes)
    except InvalidTimezone:
        # 422, как и для остальных ошибок валидации тела запроса
        raise HTTPException(422, "Неизвестный часовой пояс") from None
    return TrainerOut.of(trainer)


class ReferralOut(BaseModel):
    id: int
    display_name: str
    avatar_url: str | None
    joined_at: datetime
    # Оплачивал ли Pro и сколько рублей принёс на баланс
    paid: bool
    earned: int


class ReferralsOut(BaseModel):
    # Личная ссылка для коллег: многоразовая и бессрочная
    url: str
    trainers: list[ReferralOut]
    # Сколько процентов с оплат приглашённых идёт на баланс
    percent: int
    balance: int
    earned: int


@router.get("/referrals")
async def get_referrals(trainer: CurrentTrainer, session: SessionDep) -> ReferralsOut:
    """Ссылка «Пригласить тренера» и кто по ней пришёл."""
    invited = await list_referrals(session, trainer)
    earnings = await billing.referral_earnings(session, trainer)
    paid = await billing.paid_trainers(session, [t.id for t in invited])
    return ReferralsOut(
        url=referral_link(await get_bot_username(), trainer),
        trainers=[
            ReferralOut(
                id=t.id,
                display_name=t.display_name,
                avatar_url=avatars.avatar_url(t.user),
                joined_at=t.created_at,
                paid=t.id in paid,
                earned=earnings.get(t.id, 0),
            )
            for t in invited
        ],
        percent=billing.REFERRAL_PERCENT,
        balance=trainer.balance,
        earned=sum(earnings.values()),
    )


class PlanOut(BaseModel):
    key: str
    days: int
    price: int
    # С учётом баланса: сколько спишется с него и сколько заплатить деньгами
    balance_used: int
    amount: int


class DiscountOut(BaseModel):
    code: str
    # percent или rubles
    kind: str
    value: int


class SubscriptionOut(BaseModel):
    # admin, pro, trial или free
    state: str
    # Когда закончится Pro или пробный период
    until: datetime | None
    clients: int
    # Сколько клиентов можно на текущем тарифе; None — без ограничений
    client_limit: int | None
    can_add_client: bool
    free_client_limit: int
    plans: list[PlanOut]
    # Рубли на балансе: спишутся при оплате
    balance: int
    # Можно ли сейчас оплатить по СБП
    payments_enabled: bool
    # Скидка по промокоду: уже учтена в цене тарифов
    discount: DiscountOut | None = None


async def _subscription(session: SessionDep, trainer: Trainer) -> SubscriptionOut:
    sub = await subscription.get_subscription(session, trainer, datetime.now(UTC))
    terms = await subscription.get_terms(session)
    pending = await promo_codes.pending_discount(session, trainer)
    plans = []
    for key, plan in subscription.plans(terms).items():
        price = await billing.price_for(session, trainer, plan.price)
        used, amount = billing.split_price(price, trainer.balance)
        plans.append(
            PlanOut(key=key, days=plan.days, price=price, balance_used=used, amount=amount)
        )
    return SubscriptionOut(
        state=sub.state.value,
        until=sub.until,
        clients=sub.clients,
        client_limit=sub.client_limit,
        can_add_client=sub.can_add_client,
        free_client_limit=terms.free_client_limit,
        plans=plans,
        balance=trainer.balance,
        payments_enabled=get_settings().payments_enabled,
        discount=(
            DiscountOut(code=pending.code.code, kind=pending.code.kind, value=pending.code.value)
            if pending is not None
            else None
        ),
    )


@router.get("/subscription")
async def get_subscription(trainer: CurrentTrainer, session: SessionDep) -> SubscriptionOut:
    return await _subscription(session, trainer)


class PromoCodeIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)


@router.post("/promo-code")
async def redeem_promo_code(
    body: PromoCodeIn, trainer: CurrentTrainer, session: SessionDep
) -> SubscriptionOut:
    """Промокод: дни Pro добавляются сразу, скидка ждёт следующей оплаты."""
    try:
        await promo_codes.redeem(session, trainer, body.code, datetime.now(UTC))
    except promo_codes.CodeRejected as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, promo_codes.ERROR_TEXT[error.reason]
        ) from None
    return await _subscription(session, trainer)
