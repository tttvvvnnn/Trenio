import { useState } from 'react'

import { errorText, deleteAccount, giveConsent, type LegalDoc } from '../api'
import { LEGAL_TITLES, useLegal } from '../legal'
import { closeApp, confirmAction, haptic } from '../telegram'
import { EmptyState, ErrorText, PageHeader, Row, Section, SkeletonList } from './kit'
import { MainButton } from './native'
import Screen from './Screen'

// «1. Общие положения» — заголовок раздела, «1.1. …» — обычный абзац
const HEADING = /^\d+\. \S/

/** Текст документа: первая строка — название, разделы — подзаголовки, «•» — пункты списка. */
export function LegalText({ text }: { text: string }) {
  const [, ...lines] = text.split('\n')
  return (
    <div className="legal-text">
      {lines.map((line, index) => {
        if (!line.trim()) return null
        if (HEADING.test(line)) return <h3 key={index}>{line}</h3>
        if (line.startsWith('• '))
          return (
            <p key={index} className="legal-item">
              {line}
            </p>
          )
        return <p key={index}>{line}</p>
      })}
    </div>
  )
}

export function LegalScreen({ doc, onBack }: { doc: LegalDoc; onBack: () => void }) {
  const [policy, error] = useLegal(doc)
  return (
    <Screen title={LEGAL_TITLES[doc]} onBack={onBack}>
      {policy ? (
        <Section>
          <LegalText text={policy.text} />
        </Section>
      ) : (
        !error && <SkeletonList rows={4} />
      )}
      {error && <ErrorText>{error}</ErrorText>}
    </Screen>
  )
}

function LegalRows({ onOpen }: { onOpen: (doc: LegalDoc) => void }) {
  return (
    <>
      <Row
        title={LEGAL_TITLES.terms}
        icon={{ name: 'note', color: 'var(--c-accent)' }}
        chevron
        onClick={() => onOpen('terms')}
      />
      <Row
        title={LEGAL_TITLES.privacy}
        icon={{ name: 'shield', color: 'var(--c-success)' }}
        chevron
        onClick={() => onOpen('privacy')}
      />
    </>
  )
}

/** Первый вход или новая редакция документов: без согласия приложением не пользуются. */
export function ConsentGate({ onAccepted }: { onAccepted: () => void }) {
  const [open, setOpen] = useState<LegalDoc | null>(null)
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
      setError(errorText(err))
      setSaving(false)
    }
  }

  return (
    <>
      <PageHeader
        brand
        title="Добро пожаловать"
        subtitle="Прежде чем начать, прочитайте условия Trenio и то, какие данные он хранит и зачем."
      />
      <Section footer="Нажимая «Принимаю», вы принимаете пользовательское соглашение и даёте согласие на обработку персональных данных по политике конфиденциальности.">
        <LegalRows onOpen={setOpen} />
      </Section>
      {error && <ErrorText>{error}</ErrorText>}
      {open && <LegalScreen doc={open} onBack={() => setOpen(null)} />}
      {open === null && (
        <MainButton text="Принимаю" onClick={() => void accept()} loading={saving} />
      )}
    </>
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
      setError(errorText(err))
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

type Open = LegalDoc | 'delete' | null

/** Раздел Профиля: документы и удаление аккаунта. */
export function PrivacySection({ trainer }: { trainer: boolean }) {
  const [open, setOpen] = useState<Open>(null)
  return (
    <>
      <Section title="Данные">
        <LegalRows onOpen={setOpen} />
        <Row
          title="Удалить аккаунт"
          icon={{ name: 'trash', color: 'var(--c-destructive)' }}
          chevron
          onClick={() => setOpen('delete')}
        />
      </Section>
      {(open === 'terms' || open === 'privacy') && (
        <LegalScreen doc={open} onBack={() => setOpen(null)} />
      )}
      {open === 'delete' && <DeleteAccountScreen trainer={trainer} onBack={() => setOpen(null)} />}
    </>
  )
}

/** «Документы и аккаунт» в Профиле тренера: документы и удаление аккаунта на одном экране. */
export function AccountDataScreen({ trainer, onBack }: { trainer: boolean; onBack: () => void }) {
  const [open, setOpen] = useState<Open>(null)
  return (
    <Screen title="Документы и аккаунт" onBack={onBack}>
      <Section>
        <LegalRows onOpen={setOpen} />
        <Row
          title="Удалить аккаунт"
          icon={{ name: 'trash', color: 'var(--c-destructive)' }}
          chevron
          onClick={() => setOpen('delete')}
        />
      </Section>
      {(open === 'terms' || open === 'privacy') && (
        <LegalScreen doc={open} onBack={() => setOpen(null)} />
      )}
      {open === 'delete' && <DeleteAccountScreen trainer={trainer} onBack={() => setOpen(null)} />}
    </Screen>
  )
}
