import { useEffect, useState } from 'react'

import { fetchClients, fetchInviteLink, type Client } from '../api'
import { fullName, rubles } from '../format'
import { haptic, shareLink } from '../telegram'
import { PersonAvatar } from '../ui/Avatar'
import { AddRow, EmptyState, ErrorText, PageHeader, Row, Section, SkeletonList } from '../ui/kit'
import ClientCard from './ClientCard'
import ClientForm from './ClientForm'

const SHARE_TEXT = 'Записывайтесь ко мне на тренировки в Trenio'

function since(iso: string): string {
  return new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long' }).format(new Date(iso))
}

// Что показать справа в строке клиента: остаток занятий, долг или дату появления
function clientBadge(client: Client) {
  if (client.upcoming_one_off > 0) {
    return <span className="badge alert">без блока: {client.upcoming_one_off}</span>
  }
  if (client.sessions_left !== null && client.sessions_left <= 2) {
    return <span className="badge warning">осталось {client.sessions_left}</span>
  }
  if (client.debt > 0) {
    return <span className="badge warning">долг {rubles(client.debt)}</span>
  }
  if (client.sessions_left !== null) {
    return <span className="badge success">осталось {client.sessions_left}</span>
  }
  if (client.has_packages) {
    return <span className="badge">блок закончился</span>
  }
  return undefined
}

function clientSubtitle(client: Client): string {
  if (client.offline) return `без Telegram · с ${since(client.since)}`
  if (client.username) return `@${client.username} · с ${since(client.since)}`
  return `с ${since(client.since)}`
}

type Props = {
  timezone: string
}

export default function Clients({ timezone }: Props) {
  const [clients, setClients] = useState<Client[] | null>(null)
  const [opened, setOpened] = useState<Client | null>(null)
  const [adding, setAdding] = useState(false)
  const [link, setLink] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function reloadClients() {
    fetchClients()
      .then(setClients)
      .catch((err: unknown) => setError(String(err)))
  }

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
          text="Отправьте ссылку, и клиенты появятся здесь после первого перехода. Клиента без Telegram добавьте сами."
        />
      )}
      {clients !== null && (
        <Section title={clients.length > 0 ? `Все клиенты · ${clients.length}` : undefined}>
          {clients.map((client) => (
            <Row
              key={client.id}
              title={fullName(client)}
              leading={<PersonAvatar person={client} />}
              subtitle={clientSubtitle(client)}
              onClick={() => setOpened(client)}
              badge={clientBadge(client)}
            />
          ))}
          <AddRow title="Добавить клиента без Telegram" onClick={() => setAdding(true)} />
        </Section>
      )}
      {adding && (
        <ClientForm
          onBack={() => setAdding(false)}
          onSaved={(created) => {
            setAdding(false)
            setOpened(created)
            reloadClients()
          }}
        />
      )}
      {opened && (
        <ClientCard
          client={opened}
          timezone={timezone}
          onBack={() => setOpened(null)}
          onChanged={reloadClients}
        />
      )}
    </>
  )
}
