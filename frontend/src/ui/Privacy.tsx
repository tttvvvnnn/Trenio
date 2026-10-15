import { useEffect, useState } from 'react'

import { deleteAccount, fetchPolicy, giveConsent, type Policy } from '../api'
import { closeApp, confirmAction, haptic } from '../telegram'
import { EmptyState, ErrorText, PageHeader, Row, Section, SkeletonList } from './kit'
import { MainButton } from './native'
import { RulesText } from './Rules'
import Screen from './Screen'

function usePolicy(): [Policy | null, string | null] {
  const [policy, setPolicy] = useState<Policy | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    fetchPolicy()
      .then(setPolicy)
      .catch((err: unknown) => setError(String(err)))
  }, [])
  return [policy, error]
}

/** Первый вход или новая версия политики: без согласия приложением не пользуются. */
export function ConsentGate({ onAccepted }: { onAccepted: () => void }) {
  const [policy, loadError] = usePolicy()
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function accept() {
    if (saving) return
    setSaving(true)
    setError(null)
    try {
      await giveConsent()
      haptic.success()
      onAccepted()
    } catch (err) {
      haptic.error()
      setError(err instanceof Error ? err.message : String(err))
      setSaving(false)
    }
  }

  return (
    <>
      <PageHeader
        brand
        title="Ваши данные"
        subtitle="Прежде чем начать, прочитайте, какие данные хранит Trenio и зачем."
      />
      {policy ? <RulesText text={policy.text} /> : !loadError && <SkeletonList rows={4} />}
      {(loadError || error) && <ErrorText>{loadError ?? error}</ErrorText>}
      <MainButton
        text="Согласен"
        onClick={() => void accept()}
        disabled={policy === null}
        loading={saving}
      />
    </>
  )
}

function PolicyScreen({ onBack }: { onBack: () => void }) {
  const [policy, error] = usePolicy()
  return (
    <Screen title="Обработка данных" onBack={onBack}>
      {policy ? <RulesText text={policy.text} /> : !error && <SkeletonList rows={4} />}
      {error && <ErrorText>{error}</ErrorText>}
    </Screen>
  )
}

type DeleteProps = {
  // Тренер теряет расписание и клиентов, клиент — только свои данные
  trainer: boolean
  onBack: () => void
}

function DeleteAccountScreen({ trainer, onBack }: DeleteProps) {
  const [deleting, setDeleting] = useState(false)
  const [deleted, setDeleted] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function remove() {
    if (deleting) return
    const sure = await confirmAction(
      'Удалить аккаунт? Восстановить его не получится.',
      'Удалить навсегда',
    )
    if (!sure) return
    setDeleting(true)
    setError(null)
    try {
      await deleteAccount()
      haptic.success()
      setDeleted(true)
    } catch (err) {
      haptic.error()
      setError(err instanceof Error ? err.message : String(err))
      setDeleting(false)
    }
  }

  if (deleted) {
    return (
      <div className="screen-overlay" role="dialog" aria-modal="true" aria-label="Аккаунт удалён">
        <EmptyState
          icon="check"
          title="Аккаунт удалён"
          text="Если захотите вернуться, откройте бота заново: начнёте с чистого листа."
          action={{ label: 'Закрыть', onClick: closeApp }}
        />
      </div>
    )
  }

  return (
    <Screen title="Удалить аккаунт" onBack={onBack}>
      <Section title="Что удалится">
        <p className="rules-text">
          {trainer
            ? 'Профиль тренера, услуги, расписание, все записи, блоки и оплаты, клиенты без Telegram. Клиенты с Telegram останутся в Trenio, но без вас. Ваши записи к другим тренерам отменятся, у них останется обезличенная история.'
            : 'Имя, фото, телефон, заметки тренера о вас и о занятиях, замеры и настройки. Будущие записи отменятся, тренер получит уведомление. Прошедшие занятия и оплаты останутся у тренера обезличенными, под именем «Удалённый клиент»: они нужны ему для учёта.'}
        </p>
      </Section>
      {error && <ErrorText>{error}</ErrorText>}
      <Section>
        <Row
          title={deleting ? 'Удаляем…' : 'Удалить аккаунт навсегда'}
          tone="destructive"
          centered
          onClick={deleting ? undefined : () => void remove()}
        />
      </Section>
    </Screen>
  )
}

/** Раздел Профиля: политика обработки данных и удаление аккаунта. */
export function PrivacySection({ trainer }: { trainer: boolean }) {
  const [open, setOpen] = useState<'policy' | 'delete' | null>(null)
  return (
    <>
      <Section title="Данные">
        <Row
          title="Обработка данных"
          icon={{ name: 'shield', color: 'var(--c-success)' }}
          chevron
          onClick={() => setOpen('policy')}
        />
        <Row
          title="Удалить аккаунт"
          icon={{ name: 'trash', color: 'var(--c-destructive)' }}
          chevron
          onClick={() => setOpen('delete')}
        />
      </Section>
      {open === 'policy' && <PolicyScreen onBack={() => setOpen(null)} />}
      {open === 'delete' && <DeleteAccountScreen trainer={trainer} onBack={() => setOpen(null)} />}
    </>
  )
}
