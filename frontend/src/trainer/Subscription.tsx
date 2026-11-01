import { useEffect, useRef, useState } from 'react'

import {
  errorText,
  fetchPayment,
  fetchSubscription,
  redeemPromoCode,
  startPayment,
  startTopup,
  type Subscription as Sub,
  type SubscriptionPayment,
  type SubscriptionPlan,
} from '../api'
import { plural, rubles } from '../format'
import { untilText } from '../settings'
import { useRefreshKey } from '../sync'
import { confirmAction, haptic, openUrl } from '../telegram'
import { ErrorText, Row, Section, SkeletonList, TextField } from '../ui/kit'
import { LegalScreen } from '../ui/Privacy'
import Screen from '../ui/Screen'

function stateHint(sub: Sub, timezone: string): { tone: string; text: string } | null {
  const limit = plural(sub.free_client_limit, 'клиента', 'клиентов', 'клиентов')
  switch (sub.state) {
    case 'trial':
      return {
        tone: 'planned',
        text: `Пробный период ${untilText(sub.until, timezone)}: все возможности без ограничений. Потом бесплатно можно вести до ${limit}.`,
      }
    case 'pro':
      return {
        tone: 'done',
        text: `Pro ${untilText(sub.until, timezone)}. Клиентов сколько угодно.`,
      }
    case 'free':
      return sub.can_add_client
        ? {
            tone: 'pending',
            text: `Бесплатный тариф: ${sub.clients} из ${limit}. Всё работает, но новых клиентов сверх лимита не добавить.`,
          }
        : {
            tone: 'alert',
            text: `Бесплатный тариф: у вас ${plural(sub.clients, 'клиент', 'клиента', 'клиентов')}, это лимит. Записи и блоки работают как раньше, но новых клиентов не добавить.`,
          }
    case 'admin':
      return {
        tone: 'done',
        text: 'Вы админ: Pro всегда и без оплаты. Тарифы ниже работают как у тренеров, ими можно проверить оплату.',
      }
    default:
      return null
  }
}

function discountText(discount: NonNullable<Sub['discount']>): string {
  return discount.kind === 'percent' ? `${discount.value}%` : rubles(discount.value)
}

function planTitle(plan: SubscriptionPlan): string {
  return plan.key === 'year' ? 'Pro на год' : 'Pro на месяц'
}

function planSubtitle(plan: SubscriptionPlan, month: SubscriptionPlan | undefined): string {
  const parts = [
    plan.key === 'year' && month
      ? `${rubles(Math.round(plan.price / 12))} в месяц, выгода ${rubles(month.price * 12 - plan.price)}`
      : 'Клиентов сколько угодно',
  ]
  if (plan.balance_used > 0) {
    parts.push(
      plan.amount > 0
        ? `с баланса ${rubles(plan.balance_used)}, к оплате ${rubles(plan.amount)}`
        : 'целиком с баланса',
    )
  }
  return parts.join(' · ')
}

function topupFooter(sub: Sub, amount: number): string {
  const month = sub.plans.find((plan) => plan.key === 'month')
  const after = sub.balance + (amount || 0)
  if (!month) return `После пополнения на балансе будет ${rubles(after)}.`
  return after >= month.price
    ? `После пополнения на балансе будет ${rubles(after)}, хватит на Pro на месяц.`
    : `После пополнения на балансе будет ${rubles(after)}, до месяца Pro не хватит ${rubles(month.price - after)}.`
}

type Props = {
  timezone: string
  onBack: () => void
}

/** Тариф тренера и цены Pro. */
export default function Subscription({ timezone, onBack }: Props) {
  const [sub, setSub] = useState<Sub | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Оплата, которую ждём: человек ушёл на страницу СБП
  const [payment, setPayment] = useState<SubscriptionPayment | null>(null)
  const [busy, setBusy] = useState(false)
  const [termsOpen, setTermsOpen] = useState(false)
  // Что сообщить после успешной оплаты или пополнения
  const [paidNote, setPaidNote] = useState<string | null>(null)
  // Промокод: поле открывается по нажатию, после ввода — что он дал
  const [codeOpen, setCodeOpen] = useState(false)
  const [code, setCode] = useState('')
  const [codeNote, setCodeNote] = useState<string | null>(null)
  // Пополнение баланса: поле с суммой открывается по нажатию
  const [topupOpen, setTopupOpen] = useState(false)
  const [topupAmount, setTopupAmount] = useState('')
  const refreshKey = useRefreshKey()
  const paymentId = useRef<number | null>(null)

  // Растёт после оплаты: перечитать тариф и баланс
  const [version, setVersion] = useState(0)

  useEffect(() => {
    fetchSubscription()
      .then((loaded) => {
        setSub(loaded)
        setError(null)
      })
      .catch((err: unknown) => setError(errorText(err)))
  }, [refreshKey, version])

  // Пока ждём оплату, раз в несколько секунд спрашиваем статус
  useEffect(() => {
    if (payment === null) return
    paymentId.current = payment.id
    const timer = window.setInterval(() => {
      fetchPayment(payment.id)
        .then((result) => {
          if (paymentId.current === result.id && result.status !== 'pending') {
            paymentId.current = null
            setPayment(null)
            setResult(result)
          }
        })
        .catch(() => {})
    }, 4000)
    return () => window.clearInterval(timer)
  }, [payment])

  function setResult(result: SubscriptionPayment) {
    if (result.status === 'paid') {
      haptic.success()
      setPaidNote(
        result.plan === 'topup'
          ? `Готово, баланс пополнен на ${rubles(result.amount)}.`
          : 'Готово, Pro оплачен. Спасибо, что вы с Trenio!',
      )
    } else {
      setError('Оплата не прошла. Деньги не списаны, можно попробовать ещё раз.')
    }
    setVersion((value) => value + 1)
  }

  async function buy(plan: SubscriptionPlan) {
    if (busy) return
    if (plan.amount === 0) {
      const ok = await confirmAction(
        `Оплатить ${planTitle(plan)} с баланса: ${rubles(plan.balance_used)}?`,
        'Оплатить',
      )
      if (!ok) return
    }
    haptic.tap()
    setBusy(true)
    setError(null)
    setPaidNote(null)
    try {
      const created = await startPayment(plan.key)
      if (created.status === 'pending' && created.redirect_url) {
        setPayment(created)
        openUrl(created.redirect_url)
      } else {
        setResult(created)
      }
    } catch (err) {
      haptic.error()
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  function openTopup(current: Sub) {
    // По умолчанию предлагаем ровно столько, сколько не хватает до месяца Pro
    const price = current.plans.find((plan) => plan.key === 'month')?.price ?? 0
    const missing = price - current.balance
    setTopupAmount(String(Math.max(current.topup_min, missing > 0 ? missing : price)))
    setPaidNote(null)
    setTopupOpen(true)
  }

  async function topup(current: Sub) {
    const amount = Number(topupAmount)
    if (busy) return
    if (!Number.isInteger(amount) || amount < current.topup_min || amount > current.topup_max) {
      haptic.error()
      setError(
        `Пополнить можно на сумму от ${rubles(current.topup_min)} до ${rubles(current.topup_max)}.`,
      )
      return
    }
    haptic.tap()
    setBusy(true)
    setError(null)
    try {
      const created = await startTopup(amount)
      setTopupOpen(false)
      setPayment(created)
      if (created.redirect_url) openUrl(created.redirect_url)
    } catch (err) {
      haptic.error()
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  async function applyCode() {
    if (busy || !code.trim()) return
    haptic.tap()
    setBusy(true)
    setError(null)
    try {
      const before = sub
      const updated = await redeemPromoCode(code)
      haptic.success()
      setSub(updated)
      setCode('')
      setCodeOpen(false)
      setCodeNote(
        updated.discount && updated.discount.code !== before?.discount?.code
          ? `Скидка ${discountText(updated.discount)} применится к следующей оплате.`
          : `Готово, Pro ${untilText(updated.until, timezone)}.`,
      )
    } catch (err) {
      haptic.error()
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  const hint = sub && stateHint(sub, timezone)
  const month = sub?.plans.find((plan) => plan.key === 'month')

  return (
    <Screen title="Подписка" subtitle="Pro снимает ограничение на число клиентов." onBack={onBack}>
      {error && <ErrorText>{error}</ErrorText>}
      {sub === null && !error && <SkeletonList rows={2} />}
      {paidNote && <p className="card-hint done">{paidNote}</p>}
      {!paidNote && hint && <p className={`card-hint ${hint.tone}`}>{hint.text}</p>}
      {payment && (
        <Section
          title="Ждём оплату"
          footer={`Как только банк подтвердит перевод, ${payment.plan === 'topup' ? 'баланс пополнится' : 'Pro включится'} сам. Можно закрыть этот экран.`}
        >
          <Row
            title="Открыть страницу оплаты"
            subtitle={`${rubles(payment.amount)} по СБП`}
            icon={{ name: 'wallet', color: 'var(--c-accent)' }}
            onClick={() => payment.redirect_url && openUrl(payment.redirect_url)}
          />
        </Section>
      )}
      {sub && (
        <>
          <Section title="Тарифы">
            <Row
              title="Бесплатно"
              subtitle={`До ${plural(sub.free_client_limit, 'клиента', 'клиентов', 'клиентов')}, всё остальное без ограничений`}
              icon={{ name: 'user', color: 'var(--c-hint)' }}
            />
            {sub.plans.map((plan) => (
              <Row
                key={plan.key}
                title={planTitle(plan)}
                subtitle={planSubtitle(plan, month)}
                value={rubles(plan.price)}
                icon={{ name: 'star', color: 'var(--c-warning)' }}
                chevron={sub.payments_enabled}
                onClick={sub.payments_enabled ? () => void buy(plan) : undefined}
              />
            ))}
          </Section>
          <Section
            title="Баланс"
            footer="Пополняется вашими переводами и на 20% с оплат тренеров, которых вы пригласили. Тратится только на подписку: при оплате Pro спишется сам."
          >
            <Row
              title="На балансе"
              value={rubles(sub.balance)}
              icon={{ name: 'wallet', color: 'var(--c-success)' }}
            />
            {sub.payments_enabled && !topupOpen && !payment && (
              <Row
                title="Пополнить баланс"
                icon={{ name: 'plus', color: 'var(--c-accent)' }}
                chevron
                onClick={() => openTopup(sub)}
              />
            )}
          </Section>
          {topupOpen && (
            <>
              <TextField
                label="Сумма пополнения, ₽"
                value={topupAmount}
                onChange={(value) => setTopupAmount(value.replace(/\D/g, ''))}
                inputMode="numeric"
                maxLength={5}
                footer={topupFooter(sub, Number(topupAmount))}
              />
              <Section>
                <Row
                  title={
                    busy
                      ? 'Создаём оплату…'
                      : `Пополнить на ${rubles(Number(topupAmount) || 0)} по СБП`
                  }
                  icon={{ name: 'wallet', color: 'var(--c-accent)' }}
                  onClick={() => void topup(sub)}
                />
                <Row
                  title="Отмена"
                  icon={{ name: 'x', color: 'var(--c-hint)' }}
                  onClick={() => setTopupOpen(false)}
                />
              </Section>
            </>
          )}
          {codeNote && <p className="card-hint done">{codeNote}</p>}
          {sub.discount && !codeNote && (
            <p className="card-hint done">
              Промокод {sub.discount.code}: скидка {discountText(sub.discount)} уже в цене тарифа.
            </p>
          )}
          {codeOpen ? (
            <>
              <TextField
                label="Промокод"
                value={code}
                onChange={setCode}
                maxLength={32}
                placeholder="Например, TRENIO"
                autoComplete="off"
              />
              <Section>
                <Row
                  title={busy ? 'Проверяем…' : 'Применить'}
                  icon={{ name: 'check', color: 'var(--c-accent)' }}
                  onClick={() => void applyCode()}
                />
              </Section>
            </>
          ) : (
            <Section>
              <Row
                title="Есть промокод"
                icon={{ name: 'star', color: 'var(--c-accent)' }}
                chevron
                onClick={() => {
                  setCodeNote(null)
                  setCodeOpen(true)
                }}
              />
            </Section>
          )}
          <p className="section-footer">
            {sub.payments_enabled ? (
              <>
                Нажмите на тариф, чтобы оплатить по СБП. Оплаченные дни добавятся после текущего Pro
                или пробного периода. Оплачивая, вы принимаете{' '}
                <button type="button" className="text-link" onClick={() => setTermsOpen(true)}>
                  пользовательское соглашение
                </button>
                .
              </>
            ) : (
              'Оплата сейчас недоступна, попробуйте позже.'
            )}
          </p>
        </>
      )}
      {termsOpen && <LegalScreen doc="terms" onBack={() => setTermsOpen(false)} />}
    </Screen>
  )
}
