import { useEffect, useState } from 'react'

import { errorText, fetchClients, fetchInviteLink, type Client } from '../api'
import { fullName, rubles } from '../format'
import { useRefreshKey } from '../sync'
import { haptic, shareLink } from '../telegram'
import { PersonAvatar } from '../ui/Avatar'
import { EmptyState, ErrorText, PageHeader, Row, Section, SkeletonList } from '../ui/kit'
import Screen from '../ui/Screen'
import ClientCard from './ClientCard'
import ClientForm from './ClientForm'

const SHARE_TEXT = 'Записывайтесь ко мне на тренировки в Trenio'

type Filter = 'all' | 'debt' | 'no-block' | 'ending'

const FILTERS: [Filter, string, (client: Client) => boolean][] = [
  ['all', 'Все', () => true],
  ['debt', 'Долг', (client) => client.debt > 0],
  [
    'no-block',
    'Без блока',
    (client) => !client.deleted && (client.sessions_left === null || client.upcoming_one_off > 0),
  ],
  ['ending', 'Кончается блок', (client) => client.ending_soon],
]

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

// Текущий блок и сколько пройдено; без блока — как клиент пришёл
function clientSubtitle(client: Client): string {
  if (client.deleted) return 'удалил аккаунт'
  if (client.block) {
    return `${client.block.name} · ${client.block.used} из ${client.block.sessions_count}`
  }
  if (client.offline) return `без Telegram · с ${since(client.since)}`
  if (client.username) return `@${client.username} · с ${since(client.since)}`
  return `с ${since(client.since)}`
}

// Поиск по имени, фамилии и @username, без учёта регистра и ё
function matches(client: Client, query: string): boolean {
  const normal = (text: string) => text.toLowerCase().replace(/ё/g, 'е')
  const words = normal(query).trim().split(/\s+/).filter(Boolean)
  const haystack = normal(`${fullName(client)} ${client.username ?? ''}`)
  return words.every((word) => haystack.includes(word.replace(/^@/, '')))
}

type Props = {
  timezone: string
}

export default function Clients({ timezone }: Props) {
  const [clients, setClients] = useState<Client[] | null>(null)
  const [opened, setOpened] = useState<Client | null>(null)
  const [inviting, setInviting] = useState(false)
  const [adding, setAdding] = useState(false)
  const [link, setLink] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const [error, setError] = useState<string | null>(null)
  const refreshKey = useRefreshKey()

  function reloadClients() {
    fetchClients()
      .then(setClients)
      .catch((err: unknown) => setError(errorText(err)))
  }

  useEffect(() => {
    Promise.all([fetchClients(), fetchInviteLink()])
      .then(([loadedClients, loadedLink]) => {
        setClients(loadedClients)
        setLink(loadedLink)
      })
      .catch((err: unknown) => setError(errorText(err)))
  }, [refreshKey])

  const empty = clients !== null && clients.length === 0
  const counts = new Map(
    FILTERS.map(([value, , test]) => [value, clients?.filter(test).length ?? 0]),
  )
  // Фильтр без клиентов не показываем; выбранный остаётся, пока по нему кто-то есть
  const filters = FILTERS.filter(([value]) => value === 'all' || (counts.get(value) ?? 0) > 0)
  const active = filters.find(([value]) => value === filter) ?? filters[0]
  const shown = clients?.filter((client) => active[2](client) && matches(client, query)) ?? []

  return (
    <>
      <PageHeader
        title="Клиенты"
        action={
          !empty && (
            <button
              type="button"
              className="pill-button"
              data-tour="invite-link"
              onClick={() => {
                haptic.tap()
                setInviting(true)
              }}
            >
              ＋ Пригласить
            </button>
          )
        }
      />
      {error && <ErrorText>{error}</ErrorText>}
      {clients === null && !error && <SkeletonList rows={3} />}
      {empty && (
        <>
          <EmptyState
            icon="users"
            title="Пока нет клиентов"
            text="Отправьте ссылку, и клиенты появятся здесь после первого перехода. Клиента без Telegram добавьте сами."
          />
          <InviteRows link={link} tourId="invite-link" onAdd={() => setAdding(true)} />
        </>
      )}
      {clients !== null && !empty && (
        <>
          <div className="search">
            <input
              type="search"
              placeholder="Поиск по имени"
              aria-label="Поиск по имени"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
          {filters.length > 1 && (
            <div className="chips scroll" role="radiogroup" aria-label="Каких клиентов показать">
              {filters.map(([value, title]) => (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  className="chip"
                  aria-checked={value === active[0]}
                  onClick={() => {
                    haptic.select()
                    setFilter(value)
                  }}
                >
                  {title} · {counts.get(value)}
                </button>
              ))}
            </div>
          )}
          {shown.length === 0 ? (
            <p className="section-footer">Никого не нашли.</p>
          ) : (
            <Section>
              {shown.map((client) => (
                <Row
                  key={client.id}
                  title={fullName(client)}
                  leading={<PersonAvatar person={client} />}
                  subtitle={clientSubtitle(client)}
                  tone={client.deleted ? 'muted' : undefined}
                  onClick={() => setOpened(client)}
                  badge={clientBadge(client)}
                />
              ))}
            </Section>
          )}
        </>
      )}
      {inviting && (
        <Screen title="Пригласить клиента" onBack={() => setInviting(false)}>
          <InviteRows link={link} onAdd={() => setAdding(true)} />
        </Screen>
      )}
      {adding && (
        <ClientForm
          onBack={() => setAdding(false)}
          onSaved={(created) => {
            setAdding(false)
            setInviting(false)
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

type InviteProps = {
  link: string | null
  tourId?: string
  onAdd: () => void
}

/** Ссылка тренера и клиент без Telegram: на экране «Пригласить» и в пустом списке. */
function InviteRows({ link, tourId, onAdd }: InviteProps) {
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<string | null>(null)

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
      {link && (
        <Section
          tourId={tourId}
          footer="Клиент открывает ссылку, бот добавляет его к вам, и он может записываться в окошки."
        >
          <Row
            title="Отправить ссылку"
            subtitle="В чат клиенту через Telegram"
            icon={{ name: 'share', color: 'var(--c-accent)' }}
            onClick={() => {
              haptic.tap()
              shareLink(link, SHARE_TEXT)
            }}
          />
          <Row
            title={copied ? 'Скопировано' : 'Скопировать ссылку'}
            subtitle={link.replace('https://', '')}
            icon={{ name: 'copy', color: 'var(--c-violet)' }}
            onClick={() => void copy()}
          />
        </Section>
      )}
      {error && <ErrorText>{error}</ErrorText>}
      <Section footer="Клиент, который не пользуется Telegram. Записывать его будете вы сами.">
        <Row
          title="Добавить без Telegram"
          icon={{ name: 'plus', color: 'var(--c-success)' }}
          onClick={onAdd}
        />
      </Section>
    </>
  )
}
