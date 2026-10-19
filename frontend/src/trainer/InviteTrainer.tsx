import { useEffect, useState } from 'react'

import { errorText, fetchReferrals, type Referrals } from '../api'
import { localDate, longDate, plural, rubles } from '../format'
import { useRefreshKey } from '../sync'
import { haptic, shareLink } from '../telegram'
import Avatar from '../ui/Avatar'
import { ErrorText, Row, Section, SkeletonList } from '../ui/kit'
import Screen from '../ui/Screen'

const SHARE_TEXT = 'Веду клиентов и расписание в Trenio. Попробуй, по ссылке сразу откроется доступ'

type Props = {
  timezone: string
  onBack: () => void
}

/** Личная ссылка для коллег-тренеров и список тех, кто по ней пришёл. */
export default function InviteTrainer({ timezone, onBack }: Props) {
  const [data, setData] = useState<Referrals | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const refreshKey = useRefreshKey()

  useEffect(() => {
    fetchReferrals()
      .then((loaded) => {
        setData(loaded)
        setError(null)
      })
      .catch((err: unknown) => setError(errorText(err)))
  }, [refreshKey])

  async function copy(url: string) {
    try {
      await navigator.clipboard.writeText(url)
      haptic.success()
      setCopied(true)
    } catch {
      haptic.error()
      setError('Не удалось скопировать. Ссылка: ' + url)
    }
  }

  return (
    <Screen
      title="Пригласить тренера"
      subtitle="Коллега открывает вашу ссылку и сразу получает доступ к Trenio."
      onBack={onBack}
    >
      {error && <ErrorText>{error}</ErrorText>}
      {data === null && !error && <SkeletonList rows={2} />}
      {data && (
        <>
          <Section
            footer={`Ссылка постоянная: по ней можно пригласить сколько угодно тренеров. С каждой их оплаты Pro вам на баланс идёт ${data.percent}%, балансом можно оплатить свою подписку.`}
          >
            <Row
              title="Отправить ссылку"
              subtitle="В чат коллеге через Telegram"
              icon={{ name: 'share', color: 'var(--c-accent)' }}
              onClick={() => {
                haptic.tap()
                shareLink(data.url, SHARE_TEXT)
              }}
            />
            <Row
              title={copied ? 'Скопировано' : 'Скопировать ссылку'}
              subtitle={data.url.replace('https://', '')}
              icon={{ name: 'copy', color: 'var(--c-violet)' }}
              onClick={() => void copy(data.url)}
            />
          </Section>
          {data.earned > 0 && (
            <Section>
              <Row
                title="Баланс"
                subtitle={`Всего начислено ${rubles(data.earned)}`}
                value={rubles(data.balance)}
                icon={{ name: 'wallet', color: 'var(--c-success)' }}
              />
            </Section>
          )}
          {data.trainers.length > 0 ? (
            <Section
              title={`Пришли по ссылке · ${plural(data.trainers.length, 'тренер', 'тренера', 'тренеров')}`}
            >
              {data.trainers.map((trainer) => (
                <Row
                  key={trainer.id}
                  title={trainer.display_name}
                  subtitle={`С ${longDate(localDate(trainer.joined_at, timezone))}`}
                  value={trainer.earned > 0 ? `+${rubles(trainer.earned)}` : undefined}
                  badge={trainer.paid ? <span className="badge success">Pro</span> : undefined}
                  leading={
                    <Avatar
                      name={trainer.display_name}
                      url={trainer.avatar_url}
                      seed={trainer.id}
                    />
                  }
                />
              ))}
            </Section>
          ) : (
            <p className="section-footer">
              Здесь появятся тренеры, которые пришли по вашей ссылке.
            </p>
          )}
        </>
      )}
    </Screen>
  )
}
