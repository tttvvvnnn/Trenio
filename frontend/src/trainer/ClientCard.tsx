import { useEffect, useRef, useState } from 'react'

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
import { haptic, shareLink } from '../telegram'
import { DateLeaf } from '../ui/BookingDays'
import { PersonAvatar } from '../ui/Avatar'
import { AddRow, ErrorText, Row, Section, Segmented, SkeletonList } from '../ui/kit'
import { PackageBadge } from '../ui/PackageSummary'
import Screen from '../ui/Screen'
import { BookingBadge } from '../ui/MonthCalendar'
import BookingDetails from './BookingDetails'
import ClientForm from './ClientForm'
import ClientProgress from './ClientProgress'
import MergeClient from './MergeClient'
import NewBooking from './NewBooking'
import PackageDetails from './PackageDetails'
import PhoneForm from './PhoneForm'
import SellPackage from './SellPackage'
import { useRefreshKey } from '../sync'

type Props = {
  client: Client
  timezone: string
  onBack: () => void
  // Блоки или записи поменялись: список клиентов стоит перечитать
  onChanged: () => void
}

/** Карточка клиента: блоки, заметки и история записей, на второй вкладке — прогресс. */
export default function ClientCard({ client: initial, timezone, onBack, onChanged }: Props) {
  const [card, setCard] = useState<Card | null>(null)
  const [notes, setNotes] = useState('')
  const [notesState, setNotesState] = useState<'idle' | 'saving' | 'saved'>('idle')
  const [error, setError] = useState<string | null>(null)
  const [openedPackage, setOpenedPackage] = useState<number | null>(null)
  const [selling, setSelling] = useState(false)
  const [openedBooking, setOpenedBooking] = useState<Booking | null>(null)
  const [booking, setBooking] = useState(false)
  const [reloads, setReloads] = useState(0)
  const refreshKey = useRefreshKey()
  const notesLoaded = useRef(false)
  const [renaming, setRenaming] = useState(false)
  const [merging, setMerging] = useState(false)
  const [inviting, setInviting] = useState(false)
  const [editingPhone, setEditingPhone] = useState(false)
  const [tab, setTab] = useState<'card' | 'progress'>('card')

  // Имя клиента без Telegram тренер может поменять: свежие данные берём из карточки
  const client = card?.client ?? initial

  useEffect(() => {
    fetchClientCard(initial.id)
      .then((loaded) => {
        setCard(loaded)
        // Заметки берём с сервера только при первой загрузке: дальше их может править тренер
        if (!notesLoaded.current) setNotes(loaded.notes ?? '')
        notesLoaded.current = true
      })
      .catch((err: unknown) => setError(errorText(err)))
  }, [initial.id, reloads, refreshKey])

  function reload() {
    setReloads((count) => count + 1)
    onChanged()
  }

  async function saveNotes() {
    if (card === null || notes.trim() === (card.notes ?? '')) return
    setNotesState('saving')
    try {
      await saveClientNotes(client.id, notes.trim() || null)
      setCard({ ...card, notes: notes.trim() || null })
      setNotesState('saved')
    } catch (err) {
      haptic.error()
      setNotesState('idle')
      setError(errorText(err))
    }
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
  const pkg = card?.packages.find((item) => item.id === openedPackage) ?? null
  const summary = card?.client

  const hint = summary ? clientHint(summary) : null

  function bookingRow(item: Booking) {
    return (
      <Row
        key={item.id}
        leading={<DateLeaf day={localDate(item.starts_at, timezone)} muted={inactive(item)} />}
        title={item.service.name}
        subtitle={[localTime(item.starts_at, timezone), ...bookingState(item, now)].join(' · ')}
        tone={inactive(item) ? 'muted' : undefined}
        onClick={() => setOpenedBooking(item)}
        badge={<BookingBadge booking={item} now={now} />}
      />
    )
  }

  return (
    <Screen
      title={name}
      subtitle={
        client.deleted
          ? 'удалил аккаунт'
          : client.offline
            ? 'без Telegram'
            : client.username
              ? `@${client.username}`
              : undefined
      }
      avatar={<PersonAvatar person={client} size="md" />}
      onBack={onBack}
    >
      {error && <ErrorText>{error}</ErrorText>}
      {card === null && !error && <SkeletonList rows={3} />}
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
          onOpenBooking={setOpenedBooking}
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
          {!client.deleted && (
            <Section>
              <Row
                title={card.phone ?? 'Добавить телефон'}
                subtitle={card.phone ? 'Телефон, видите только вы' : undefined}
                tone={card.phone ? undefined : 'accent'}
                icon={{ name: 'phone', color: 'var(--c-success)' }}
                chevron
                onClick={() => setEditingPhone(true)}
              />
            </Section>
          )}
          {client.offline && (
            <Section
              title="Без Telegram"
              footer="Напоминания клиенту не приходят. Отправьте ему личную ссылку: когда он откроет её в Telegram, записи и блоки перейдут к нему."
            >
              <Row
                title={inviting ? 'Готовим ссылку…' : 'Пригласить в Telegram'}
                icon={{ name: 'share', color: 'var(--c-accent)' }}
                onClick={() => void invite()}
              />
              <Row
                title="Изменить имя"
                icon={{ name: 'user', color: 'var(--c-violet)' }}
                onClick={() => setRenaming(true)}
              />
              <Row
                title="Уже есть в Telegram"
                subtitle="Объединить с клиентом, который зашёл по ссылке"
                icon={{ name: 'users', color: 'var(--c-success)' }}
                onClick={() => setMerging(true)}
              />
            </Section>
          )}
          <Section title="Блоки">
            {card.packages.map((item: Package) => (
              <Row
                key={item.id}
                title={item.name}
                subtitle={packageLine(item)}
                tone={item.status === 'active' ? undefined : 'muted'}
                onClick={() => setOpenedPackage(item.id)}
                badge={<PackageBadge pkg={item} />}
              />
            ))}
            {!client.deleted && <AddRow title="Продать блок" onClick={() => setSelling(true)} />}
          </Section>
          {!client.deleted && (
            <section className="section">
              <label className="section-title" htmlFor="client-notes">
                Заметки
              </label>
              <div className="group">
                <textarea
                  id="client-notes"
                  className="field-input"
                  placeholder="Цели, ограничения, о чём договорились. Клиент заметки не видит."
                  maxLength={4000}
                  value={notes}
                  onChange={(event) => {
                    setNotes(event.target.value)
                    setNotesState('idle')
                  }}
                  onBlur={() => void saveNotes()}
                />
              </div>
              {notesState !== 'idle' && (
                <p className="section-footer">
                  {notesState === 'saving' ? 'Сохраняем…' : 'Сохранено'}
                </p>
              )}
            </section>
          )}
          {(!client.deleted || upcoming.length > 0) && (
            <Section title="Ближайшие">
              {upcoming.map(bookingRow)}
              {!client.deleted && (
                <AddRow title="Записать на занятие" onClick={() => setBooking(true)} />
              )}
            </Section>
          )}
          {past.length > 0 && <Section title="История">{past.map(bookingRow)}</Section>}
        </>
      )}
      {pkg && (
        <PackageDetails
          pkg={pkg}
          clientName={name}
          timezone={timezone}
          onBack={() => setOpenedPackage(null)}
          onChanged={(updated, local) => {
            if (updated === null) setOpenedPackage(null)
            else
              setCard(
                (current) =>
                  current && {
                    ...current,
                    packages: current.packages.map((item) =>
                      item.id === updated.id ? updated : item,
                    ),
                  },
              )
            // Изменение пока только на экране (ждёт «Отменить»): сервер ещё не знает
            if (!local) reload()
          }}
        />
      )}
      {selling && (
        <SellPackage
          clientId={client.id}
          clientName={name}
          timezone={timezone}
          onBack={() => setSelling(false)}
          onSold={(sold) => {
            setSelling(false)
            setOpenedPackage(sold.id)
            reload()
          }}
        />
      )}
      {booking && (
        <NewBooking
          timezone={timezone}
          client={client}
          onBack={() => setBooking(false)}
          onBooked={() => {
            setBooking(false)
            reload()
          }}
        />
      )}
      {editingPhone && card && (
        <PhoneForm
          clientId={client.id}
          clientName={name}
          phone={card.phone}
          onBack={() => setEditingPhone(false)}
          onSaved={(phone) => {
            setEditingPhone(false)
            setCard((current) => current && { ...current, phone })
          }}
        />
      )}
      {renaming && (
        <ClientForm
          client={client}
          onBack={() => setRenaming(false)}
          onSaved={() => {
            setRenaming(false)
            reload()
          }}
        />
      )}
      {merging && (
        <MergeClient
          client={client}
          onBack={() => setMerging(false)}
          onMerged={() => {
            onChanged()
            onBack()
          }}
        />
      )}
      {openedBooking && (
        <BookingDetails
          booking={openedBooking}
          onBack={() => setOpenedBooking(null)}
          onChanged={(updated) => {
            setOpenedBooking(updated)
            reload()
          }}
        />
      )}
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
