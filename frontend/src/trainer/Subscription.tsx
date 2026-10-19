import { useEffect, useState } from 'react'

import { errorText, fetchSubscription, type Subscription as Sub } from '../api'
import { plural, rubles } from '../format'
import { untilText } from '../settings'
import { useRefreshKey } from '../sync'
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

type Props = {
  timezone: string
  onBack: () => void
}

/** Тариф тренера и цены Pro. */
export default function Subscription({ timezone, onBack }: Props) {
  const [sub, setSub] = useState<Sub | null>(null)
  const [error, setError] = useState<string | null>(null)
  const refreshKey = useRefreshKey()

  useEffect(() => {
    fetchSubscription()
      .then((loaded) => {
        setSub(loaded)
        setError(null)
      })
      .catch((err: unknown) => setError(errorText(err)))
  }, [refreshKey])

  const hint = sub && stateHint(sub, timezone)
  const month = sub?.plans.find((plan) => plan.key === 'month')

  return (
    <Screen title="Подписка" subtitle="Pro снимает ограничение на число клиентов." onBack={onBack}>
      {error && <ErrorText>{error}</ErrorText>}
      {sub === null && !error && <SkeletonList rows={2} />}
      {hint && <p className={`card-hint ${hint.tone}`}>{hint.text}</p>}
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
                title={plan.key === 'year' ? 'Pro на год' : 'Pro на месяц'}
                subtitle={
                  plan.key === 'year' && month
                    ? `${rubles(Math.round(plan.price / 12))} в месяц, выгода ${rubles(month.price * 12 - plan.price)}`
                    : 'Клиентов сколько угодно'
                }
                value={rubles(plan.price)}
                icon={{ name: 'star', color: 'var(--c-warning)' }}
              />
            ))}
          </Section>
          <p className="section-footer">
            Оплата по СБП появится в ближайшем обновлении. Оплаченные дни добавятся после текущего
            Pro или пробного периода.
          </p>
        </>
      )}
    </Screen>
  )
}
