import { useEffect, useState } from 'react'

import {
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
import { haptic } from '../telegram'
import { DateLeaf } from '../ui/BookingDays'
import { PersonAvatar } from '../ui/Avatar'
import { AddRow, ErrorText, Row, Section, SkeletonList } from '../ui/kit'
import { PackageBadge } from '../ui/PackageSummary'
import Screen from '../ui/Screen'
import { BookingBadge } from '../ui/MonthCalendar'
import BookingDetails from './BookingDetails'
import NewBooking from './NewBooking'
import PackageDetails from './PackageDetails'
import SellPackage from './SellPackage'

type Props = {
  client: Client
  timezone: string
  onBack: () => void
  // Блоки или записи поменялись: список клиентов стоит перечитать
  onChanged: () => void
}

/** Карточка клиента: блоки, заметки и история записей. */
export default function ClientCard({ client, timezone, onBack, onChanged }: Props) {
  const [card, setCard] = useState<Card | null>(null)
  const [notes, setNotes] = useState('')
  const [notesState, setNotesState] = useState<'idle' | 'saving' | 'saved'>('idle')
  const [error, setError] = useState<string | null>(null)
  const [openedPackage, setOpenedPackage] = useState<number | null>(null)
  const [selling, setSelling] = useState(false)
  const [openedBooking, setOpenedBooking] = useState<Booking | null>(null)
  const [booking, setBooking] = useState(false)
  const [reloads, setReloads] = useState(0)

  useEffect(() => {
    fetchClientCard(client.id)
      .then((loaded) => {
        setCard(loaded)
        setNotes((current) => (reloads === 0 ? (loaded.notes ?? '') : current))
      })
      .catch((err: unknown) => setError(String(err)))
  }, [client.id, reloads])

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
      setError(err instanceof Error ? err.message : String(err))
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
      subtitle={client.username ? `@${client.username}` : undefined}
      avatar={<PersonAvatar person={client} size="md" />}
      onBack={onBack}
    >
      {error && <ErrorText>{error}</ErrorText>}
      {card === null && !error && <SkeletonList rows={3} />}
      {card !== null && (
        <>
          {hint && <p className={`card-hint ${hint.tone}`}>{hint.text}</p>}
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
            <AddRow title="Продать блок" onClick={() => setSelling(true)} />
          </Section>
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
          <Section title="Ближайшие">
            {upcoming.map(bookingRow)}
            <AddRow title="Записать на занятие" onClick={() => setBooking(true)} />
          </Section>
          {past.length > 0 && <Section title="История">{past.map(bookingRow)}</Section>}
        </>
      )}
      {pkg && (
        <PackageDetails
          pkg={pkg}
          clientName={name}
          timezone={timezone}
          onBack={() => setOpenedPackage(null)}
          onChanged={(updated) => {
            if (updated === null) setOpenedPackage(null)
            reload()
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
