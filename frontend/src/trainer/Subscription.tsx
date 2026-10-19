import { useEffect, useRef, useState } from 'react'

import {
  errorText,
  fetchPayment,
  fetchSubscription,
  startPayment,
  type Subscription as Sub,
  type SubscriptionPayment,
  type SubscriptionPlan,
} from '../api'
import { plural, rubles } from '../format'
import { untilText } from '../settings'
import { useRefreshKey } from '../sync'
import { confirmAction, haptic, openUrl } from '../telegram'
import { ErrorText, Row, Section, SkeletonList } from '../ui/kit'
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
    default:
      return null
  }
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
  const [paid, setPaid] = useState(false)
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
      setPaid(true)
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
    setPaid(false)
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

  const hint = sub && stateHint(sub, timezone)
  const month = sub?.plans.find((plan) => plan.key === 'month')

  return (
    <Screen title="Подписка" subtitle="Pro снимает ограничение на число клиентов." onBack={onBack}>
      {error && <ErrorText>{error}</ErrorText>}
      {sub === null && !error && <SkeletonList rows={2} />}
      {paid && <p className="card-hint done">Готово, Pro оплачен. Спасибо, что вы с Trenio!</p>}
      {!paid && hint && <p className={`card-hint ${hint.tone}`}>{hint.text}</p>}
      {payment && (
        <Section
          title="Ждём оплату"
          footer="Как только банк подтвердит перевод, Pro включится сам. Можно закрыть этот экран."
        >
          <Row
            title="Открыть страницу оплаты"
            subtitle={`${rubles(payment.amount)} по СБП`}
            icon={{ name: 'wallet', color: 'var(--c-accent)' }}
            onClick={() => payment.redirect_url && openUrl(payment.redirect_url)}
          />
        </Section>
      )}
      {sub && sub.state !== 'admin' && (
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
          {sub.balance > 0 && (
            <Section footer="Баланс пополняется на 20% с каждой оплаты тренеров, которых вы пригласили. Он тратится только на подписку.">
              <Row
                title="Баланс"
                subtitle="Спишется при оплате"
                value={rubles(sub.balance)}
                icon={{ name: 'wallet', color: 'var(--c-success)' }}
              />
            </Section>
          )}
          <p className="section-footer">
            {sub.payments_enabled
              ? 'Нажмите на тариф, чтобы оплатить по СБП. Оплаченные дни добавятся после текущего Pro или пробного периода.'
              : 'Оплата сейчас недоступна, попробуйте позже.'}
          </p>
        </>
      )}
    </Screen>
  )
}
