import { useEffect, useState } from 'react'

import {
  errorText,
  fetchClaimLink,
  fetchClientCard,
  saveClientNotes,
  type Booking,
  type Client,
  type ClientCard as Card,
  type Package,
} from '../api'
import {
  bookingState,
  fullName,
  localDate,
  localTime,
  packageLine,
  plural,
  sessionsLeft,
} from '../format'
import { useRefreshKey } from '../sync'
import { haptic, openTelegram, shareLink } from '../telegram'
import { DateLeaf } from '../ui/BookingDays'
import { PersonAvatar } from '../ui/Avatar'
import Icon, { type IconName } from '../ui/icons'
import { ErrorText, Row, Section, Segmented, SkeletonList } from '../ui/kit'
import Menu from '../ui/Menu'
import { BookingBadge } from '../ui/MonthCalendar'
import { MainButton } from '../ui/native'
import { PackageBadge } from '../ui/PackageSummary'
import Screen from '../ui/Screen'
import BookingDetails from './BookingDetails'
import BookingSwipe from './BookingSwipe'
import ClientForm from './ClientForm'
import ClientProgress from './ClientProgress'
import MergeClient from './MergeClient'
import NewBooking from './NewBooking'
import PackageDetails from './PackageDetails'
import PhoneForm from './PhoneForm'
import SellPackage from './SellPackage'

type Props = {
  client: Client
  timezone: string
  onBack: () => void
  // Блоки или записи поменялись: список клиентов стоит перечитать
  onChanged: () => void
}

// Столько последних занятий видно в карточке, остальные — на экране «Вся история»
const HISTORY_SHOWN = 3

type Opened =
  | 'sell'
  | 'book'
  | 'phone'
  | 'notes'
  | 'rename'
  | 'merge'
  | 'history'
  | { booking: Booking }
  | { pkg: number }
  | null

/** Карточка клиента: быстрые действия, блоки, заметки и занятия, на второй вкладке — прогресс. */
export default function ClientCard({ client: initial, timezone, onBack, onChanged }: Props) {
  const [card, setCard] = useState<Card | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [opened, setOpened] = useState<Opened>(null)
  const [oldBlocks, setOldBlocks] = useState(false)
  const [inviting, setInviting] = useState(false)
  const [reloads, setReloads] = useState(0)
  const refreshKey = useRefreshKey()
  const [tab, setTab] = useState<'card' | 'progress'>('card')

  // Имя клиента без Telegram тренер может поменять: свежие данные берём из карточки
  const client = card?.client ?? initial

  useEffect(() => {
    fetchClientCard(initial.id)
      .then(setCard)
      .catch((err: unknown) => setError(errorText(err)))
  }, [initial.id, reloads, refreshKey])

  function reload() {
    setReloads((count) => count + 1)
    onChanged()
  }

  function close() {
    setOpened(null)
  }

  async function invite() {
    if (inviting) return
    setInviting(true)
    try {
      const url = await fetchClaimLink(client.id)
      haptic.tap()
      shareLink(url, 'Ваша ссылка в Trenio: откройте её, чтобы видеть свои записи и блоки')
    } catch (err) {
      haptic.error()
      setError(errorText(err))
    } finally {
      setInviting(false)
    }
  }

  const name = fullName(client)
  const now = new Date()
  const upcoming =
    card?.history
      .filter((b) => new Date(b.starts_at) > now && ['pending', 'confirmed'].includes(b.status))
      .reverse() ?? []
  const past = card?.history.filter((b) => new Date(b.starts_at) <= now) ?? []
  const current = card?.packages.filter((item) => item.status === 'active') ?? []
  const finished = card?.packages.filter((item) => item.status !== 'active') ?? []
  const pkg =
    opened && typeof opened === 'object' && 'pkg' in opened
      ? (card?.packages.find((item) => item.id === opened.pkg) ?? null)
      : null
  const openedBooking =
    opened && typeof opened === 'object' && 'booking' in opened ? opened.booking : null
  const hint = card ? clientHint(card.client) : null

  function bookingRow(item: Booking) {
    return (
      <BookingSwipe key={item.id} booking={item} onChanged={reload} onError={setError}>
        <Row
          leading={<DateLeaf day={localDate(item.starts_at, timezone)} muted={inactive(item)} />}
          title={item.service.name}
          subtitle={[localTime(item.starts_at, timezone), ...bookingState(item, now)].join(' · ')}
          tone={inactive(item) ? 'muted' : undefined}
          onClick={() => setOpened({ booking: item })}
          badge={<BookingBadge booking={item} now={now} />}
        />
      </BookingSwipe>
    )
  }

  function packageRow(item: Package) {
    return (
      <Row
        key={item.id}
        title={item.name}
        subtitle={packageLine(item)}
        tone="muted"
        onClick={() => setOpened({ pkg: item.id })}
        badge={<PackageBadge pkg={item} />}
      />
    )
  }

  const subtitle = client.deleted
    ? 'удалил аккаунт'
    : client.offline
      ? 'без Telegram'
      : [client.username && `@${client.username}`, `с ${since(client.since)}`]
          .filter(Boolean)
          .join(' · ')

  return (
    <Screen
      title={name}
      onBack={onBack}
      header={
        <div className="person-head">
          <PersonAvatar person={client} size="md" />
          <div>
            <h1>{name}</h1>
            <p>{subtitle}</p>
          </div>
          {client.offline && (
            <Menu
              label="Ещё"
              items={[
                { label: 'Изменить имя', onClick: () => setOpened('rename') },
                { label: 'Уже есть в Telegram', onClick: () => setOpened('merge') },
              ]}
            />
          )}
        </div>
      }
    >
      {error && <ErrorText>{error}</ErrorText>}
      {card === null && !error && <SkeletonList rows={3} />}
      {card !== null && client.offline && (
        <Section>
          <Row
            title={inviting ? 'Готовим ссылку…' : 'Пригласить в Telegram'}
            subtitle="Тогда придут напоминания, а записи и блоки перейдут к клиенту"
            icon={{ name: 'share', color: 'var(--c-accent)' }}
            onClick={() => void invite()}
          />
        </Section>
      )}
      {card !== null && !client.deleted && (
        <div className="quick-actions">
          <QuickAction icon="plus" label="Записать" onClick={() => setOpened('book')} />
          <QuickAction icon="ticket" label="Продать блок" onClick={() => setOpened('sell')} />
          <QuickAction
            icon="send"
            label="Написать"
            disabled={!client.username}
            onClick={() => openTelegram(`https://t.me/${client.username}`)}
          />
          <QuickAction
            icon="phone"
            label={card.phone ? 'Телефон' : '＋ Телефон'}
            onClick={() => setOpened('phone')}
          />
        </div>
      )}
      {card !== null && !client.deleted && (
        <Segmented
          label="Что показать"
          value={tab}
          options={[
            ['card', 'Карточка'],
            ['progress', 'Прогресс'],
          ]}
          onChange={setTab}
        />
      )}
      {card !== null && tab === 'progress' && !client.deleted && (
        <ClientProgress
          clientId={client.id}
          clientName={name}
          timezone={timezone}
          history={card.history}
          onOpenBooking={(booking) => setOpened({ booking })}
        />
      )}
      {card !== null && (tab === 'card' || client.deleted) && (
        <>
          {client.deleted && (
            <p className="card-hint missed">
              Клиент удалил аккаунт. Его прошедшие занятия и оплаты остались для учёта, записать его
              больше нельзя.
            </p>
          )}
          {hint && !client.deleted && <p className={`card-hint ${hint.tone}`}>{hint.text}</p>}
          {current.length > 0 && (
            <Section title="Блок">
              {current.map((item) => (
                <BlockCard key={item.id} pkg={item} onClick={() => setOpened({ pkg: item.id })} />
              ))}
            </Section>
          )}
          {finished.length > 0 && (
            <Section title={current.length === 0 ? 'Блоки' : undefined}>
              {oldBlocks ? (
                finished.map(packageRow)
              ) : (
                <Row
                  title={`Прошлые блоки · ${finished.length}`}
                  tone="accent"
                  chevron
                  onClick={() => setOldBlocks(true)}
                />
              )}
            </Section>
          )}
          {!client.deleted && (
            <Section>
              <Row
                title="Заметки"
                subtitle={card.notes ?? 'Цели, ограничения, о чём договорились'}
                icon={{ name: 'note', color: 'var(--c-violet)' }}
                chevron
                onClick={() => setOpened('notes')}
              />
            </Section>
          )}
          {upcoming.length > 0 && <Section title="Ближайшие">{upcoming.map(bookingRow)}</Section>}
          {past.length > 0 && (
            <Section title="История">
              {past.slice(0, HISTORY_SHOWN).map(bookingRow)}
              {past.length > HISTORY_SHOWN && (
                <Row
                  title={`Вся история · ${past.length}`}
                  tone="accent"
                  chevron
                  onClick={() => setOpened('history')}
                />
              )}
            </Section>
          )}
        </>
      )}
      {opened === 'history' && (
        <Screen title="Вся история" subtitle={name} onBack={close}>
          <Section>{past.map(bookingRow)}</Section>
        </Screen>
      )}
      {opened === 'notes' && card && (
        <NotesScreen
          clientId={client.id}
          clientName={name}
          notes={card.notes}
          onBack={close}
          onSaved={(notes) => {
            close()
            setCard((value) => value && { ...value, notes })
          }}
        />
      )}
      {pkg && (
        <PackageDetails
          pkg={pkg}
          clientName={name}
          timezone={timezone}
          onBack={close}
          onChanged={(updated, local) => {
            if (updated === null) close()
            else
              setCard(
                (value) =>
                  value && {
                    ...value,
                    packages: value.packages.map((item) =>
                      item.id === updated.id ? updated : item,
                    ),
                  },
              )
            // Изменение пока только на экране (ждёт «Отменить»): сервер ещё не знает
            if (!local) reload()
          }}
        />
      )}
      {opened === 'sell' && (
        <SellPackage
          clientId={client.id}
          clientName={name}
          timezone={timezone}
          onBack={close}
          onSold={(sold) => {
            setOpened({ pkg: sold.id })
            reload()
          }}
        />
      )}
      {opened === 'book' && (
        <NewBooking
          timezone={timezone}
          client={client}
          onBack={close}
          onBooked={() => {
            close()
            reload()
          }}
        />
      )}
      {opened === 'phone' && card && (
        <PhoneForm
          clientId={client.id}
          clientName={name}
          phone={card.phone}
          onBack={close}
          onSaved={(phone) => {
            close()
            setCard((value) => value && { ...value, phone })
          }}
        />
      )}
      {opened === 'rename' && (
        <ClientForm
          client={client}
          onBack={close}
          onSaved={() => {
            close()
            reload()
          }}
        />
      )}
      {opened === 'merge' && (
        <MergeClient
          client={client}
          onBack={close}
          onMerged={() => {
            onChanged()
            onBack()
          }}
        />
      )}
      {openedBooking && (
        <BookingDetails
          booking={openedBooking}
          onBack={close}
          onChanged={(updated) => {
            setOpened({ booking: updated })
            reload()
          }}
        />
      )}
    </Screen>
  )
}

function since(iso: string): string {
  return new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long' }).format(new Date(iso))
}

type QuickActionProps = {
  icon: IconName
  label: string
  disabled?: boolean
  onClick: () => void
}

function QuickAction({ icon, label, disabled, onClick }: QuickActionProps) {
  return (
    <button
      type="button"
      className="quick-action"
      disabled={disabled}
      onClick={() => {
        haptic.tap()
        onClick()
      }}
    >
      <Icon name={icon} />
      {label}
    </button>
  )
}

/** Действующий блок: сколько пройдено полоской, оплата и срок. */
function BlockCard({ pkg, onClick }: { pkg: Package; onClick: () => void }) {
  const done = Math.min(pkg.used / pkg.sessions_count, 1)
  return (
    <button type="button" className="block-card" onClick={onClick}>
      <span className="block-card-top">
        <strong>{pkg.name}</strong>
        <PackageBadge pkg={pkg} />
      </span>
      <span className="block-card-line">{packageLine(pkg)}</span>
      <span className="block-bar" aria-hidden="true">
        <i style={{ width: `${Math.max(done * 100, 2)}%` }} />
      </span>
    </button>
  )
}

type NotesProps = {
  clientId: number
  clientName: string
  notes: string | null
  onBack: () => void
  onSaved: (notes: string | null) => void
}

/** Заметки о клиенте: видит только тренер. */
function NotesScreen({ clientId, clientName, notes, onBack, onSaved }: NotesProps) {
  const [text, setText] = useState(notes ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const next = text.trim() || null

  async function save() {
    if (saving) return
    setSaving(true)
    setError(null)
    try {
      await saveClientNotes(clientId, next)
      haptic.success()
      onSaved(next)
    } catch (err) {
      haptic.error()
      setError(errorText(err))
      setSaving(false)
    }
  }

  return (
    <Screen title="Заметки" subtitle={clientName} onBack={onBack}>
      <Section footer="Клиент заметки не видит.">
        <textarea
          className="field-input notes-input"
          aria-label="Заметки"
          placeholder="Цели, ограничения, о чём договорились"
          maxLength={4000}
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
      </Section>
      {error && <ErrorText>{error}</ErrorText>}
      <MainButton
        text="Сохранить"
        onClick={() => void save()}
        visible={next !== notes}
        loading={saving}
      />
    </Screen>
  )
}

// Главное о блоках клиента одной строкой: записи без блока, конец блока
function clientHint(client: Client): { text: string; tone: 'alert' | 'pending' } | null {
  const left = client.sessions_left
  if (client.upcoming_one_off > 0) {
    const bookings = plural(client.upcoming_one_off, 'запись', 'записи', 'записей')
    const reason = left === null ? 'Блок закончился' : 'Оставшиеся занятия блока уже заняты'
    return {
      text: `${reason}, а впереди ещё ${bookings} без блока. Предложите новый блок.`,
      tone: 'alert',
    }
  }
  if (left !== null && left <= 2) {
    return { text: `У клиента ${sessionsLeft(left)}. Пора предложить новый блок.`, tone: 'pending' }
  }
  if (client.has_packages && left === null) {
    return { text: 'Блок закончился. Новые записи будут без блока.', tone: 'pending' }
  }
  return null
}

// Отменённая или отклонённая без отметки: серым
function inactive(booking: Booking): boolean {
  return (booking.status === 'cancelled' || booking.status === 'declined') && !booking.attendance
}
