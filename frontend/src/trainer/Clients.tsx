import { useEffect, useState } from 'react'

import { fetchClients, fetchInviteLink, type Client } from '../api'
import { fullName } from '../format'
import { haptic, shareLink } from '../telegram'
import { EmptyState, ErrorText, PageHeader, Row, Section, SkeletonList } from '../ui/kit'

const SHARE_TEXT = 'Записывайтесь ко мне на тренировки в Trenio'

function since(iso: string): string {
  return new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long' }).format(new Date(iso))
}

export default function Clients() {
  const [clients, setClients] = useState<Client[] | null>(null)
  const [link, setLink] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([fetchClients(), fetchInviteLink()])
      .then(([loadedClients, loadedLink]) => {
        setClients(loadedClients)
        setLink(loadedLink)
      })
      .catch((err: unknown) => setError(String(err)))
  }, [])

  async function copy() {
    if (!link) return
    try {
      await navigator.clipboard.writeText(link)
      haptic.success()
      setCopied(true)
    } catch {
      haptic.error()
      setError('Не удалось скопировать. Ссылка: ' + link)
    }
  }

  return (
    <>
      <PageHeader title="Клиенты" />
      {error && <ErrorText>{error}</ErrorText>}
      {clients === null && !error && <SkeletonList rows={2} />}
      {link && (
        <Section
          title="Ваша ссылка"
          footer="Клиент открывает ссылку, бот добавляет его к вам, и он может записываться в окошки."
        >
          <Row
            title="Отправить ссылку"
            icon={{ name: 'share', color: 'var(--c-accent)' }}
            onClick={() => {
              haptic.tap()
              shareLink(link, SHARE_TEXT)
            }}
          />
          <Row
            title={copied ? 'Скопировано' : 'Скопировать'}
            subtitle={link.replace('https://', '')}
            icon={{ name: 'copy', color: 'var(--c-violet)' }}
            onClick={() => void copy()}
          />
        </Section>
      )}
      {clients !== null && clients.length === 0 && (
        <EmptyState
          icon="users"
          title="Пока нет клиентов"
          text="Отправьте ссылку, и клиенты появятся здесь после первого перехода."
        />
      )}
      {clients !== null && clients.length > 0 && (
        <Section title={`Все клиенты · ${clients.length}`}>
          {clients.map((client) => (
            <Row
              key={client.id}
              title={fullName(client)}
              subtitle={client.username ? `@${client.username}` : undefined}
              value={`с ${since(client.since)}`}
            />
          ))}
        </Section>
      )}
    </>
  )
}
