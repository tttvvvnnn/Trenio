import { useEffect, useState } from 'react'

import {
  fetchPendingBookings,
  fetchServices,
  fetchSlots,
  fetchTrainerBookings,
  type Booking,
  type Service,
  type Slot,
} from '../api'
import {
  addDays,
  dateTime,
  dayTitle,
  duration,
  fullName,
  localDate,
  localTime,
  plural,
} from '../format'
import { haptic } from '../telegram'
import DateStrip from '../ui/DateStrip'
import { EmptyState, ErrorText, PageHeader, Row, Section, SkeletonList } from '../ui/kit'
import StatusBadge from '../ui/StatusBadge'
import BookClient from './BookClient'
import BookingDetails from './BookingDetails'

// Сколько дней вперёд показываем окошки и записи
const DAYS = 14

type Props = {
  timezone: string
  onGoToSetup: () => void
}

type Data = {
  slots: Slot[]
  services: Service[]
  bookings: Booking[]
  pending: Booking[]
}

function isActive(booking: Booking): boolean {
  return booking.status === 'pending' || booking.status === 'confirmed'
}

export default function Calendar({ timezone, onGoToSetup }: Props) {
  const [data, setData] = useState<Data | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [opened, setOpened] = useState<Booking | null>(null)
  const [booking, setBooking] = useState<Slot | null>(null)
  // Увеличиваем, чтобы перечитать данные после изменений
  const [reloads, setReloads] = useState(0)

  useEffect(() => {
    Promise.all([
      fetchSlots(DAYS),
      fetchServices(),
      fetchTrainerBookings(DAYS),
      fetchPendingBookings(),
    ])
      .then(([slots, services, bookings, pending]) =>
        setData({ slots, services, bookings, pending }),
      )
      .catch((err: unknown) => setError(String(err)))
  }, [reloads])

  function reload() {
    setOpened(null)
    setBooking(null)
    setReloads((count) => count + 1)
  }

  const header = (
    <PageHeader title="Записи" subtitle="Записи клиентов и свободное время на 2 недели." />
  )

  if (data === null) {
    return (
      <>
        {header}
        {error ? <ErrorText>{error}</ErrorText> : <SkeletonList rows={2} />}
      </>
    )
  }

  const { slots, services, bookings, pending } = data
  if (slots.length === 0 && !bookings.some(isActive)) {
    return (
      <>
        <PageHeader title="Записи" />
        <EmptyState
          icon="calendar"
          title="Пока нет свободного времени"
          text="Добавьте услугу и рабочие часы, и окошки появятся здесь."
          action={{ label: 'Настроить расписание', onClick: onGoToSetup }}
        />
      </>
    )
  }

  const slotsByDay = new Map<string, Slot[]>()
  for (const slot of slots) {
    const day = localDate(slot.starts_at, timezone)
    slotsByDay.set(day, [...(slotsByDay.get(day) ?? []), slot])
  }
  const bookingsByDay = new Map<string, Booking[]>()
  // Отклонённые не показываем в дне: они ничего не занимают и есть у клиента
  for (const item of bookings.filter((booking) => booking.status !== 'declined')) {
    const day = localDate(item.starts_at, timezone)
    bookingsByDay.set(day, [...(bookingsByDay.get(day) ?? []), item])
  }
  const count = (day: string) =>
    (slotsByDay.get(day)?.length ?? 0) + (bookingsByDay.get(day)?.filter(isActive).length ?? 0)

  const today = localDate(new Date(), timezone)
  const days = Array.from({ length: DAYS }, (_, index) => addDays(today, index))
  // По умолчанию открыт ближайший день, где что-то есть
  const current = selected ?? days.find((day) => count(day) > 0) ?? today
  const daySlots = slotsByDay.get(current) ?? []
  const dayBookings = bookingsByDay.get(current) ?? []
  const serviceName = (id: number) => services.find((service) => service.id === id)?.name ?? ''

  return (
    <>
      {header}
      {pending.length > 0 && (
        <Section title="Ждут подтверждения">
          {pending.map((item) => (
            <Row
              key={item.id}
              title={dateTime(item.starts_at, timezone)}
              subtitle={`${fullName(item.client)} · ${item.service.name}`}
              icon={{ name: 'clock', color: 'var(--c-warning)' }}
              chevron
              onClick={() => setOpened(item)}
            />
          ))}
        </Section>
      )}
      <DateStrip days={days} current={current} count={count} onSelect={setSelected} />
      <h2 className="section-title day-title">{dayTitle(current)}</h2>
      {dayBookings.length === 0 && daySlots.length === 0 && (
        <p className="section-footer">В этот день нет записей и свободного времени.</p>
      )}
      {dayBookings.length > 0 && (
        <div className="group">
          {dayBookings.map((item) => (
            <Row
              key={item.id}
              title={`${localTime(item.starts_at, timezone)} · ${fullName(item.client)}`}
              subtitle={item.service.name}
              tone={isActive(item) ? undefined : 'muted'}
              onClick={() => setOpened(item)}
              after={<StatusBadge status={item.status} />}
            />
          ))}
        </div>
      )}
      {daySlots.length > 0 && (
        <Section title="Свободно" footer="Нажмите на время, чтобы записать клиента самому.">
          {services
            .filter((service) => daySlots.some((slot) => slot.service_id === service.id))
            .map((service) => (
              <div key={service.id} className="slot-group">
                <div className="service-head">
                  <strong>{service.name}</strong>
                  <span>
                    {duration(service.duration_min)}
                    {service.capacity > 1 && ` · до ${service.capacity} чел.`}
                  </span>
                </div>
                <div className="times">
                  {daySlots
                    .filter((slot) => slot.service_id === service.id)
                    .map((slot) => (
                      <button
                        key={slot.starts_at}
                        type="button"
                        className="time"
                        onClick={() => {
                          haptic.select()
                          setBooking(slot)
                        }}
                      >
                        {localTime(slot.starts_at, timezone)}
                        {service.capacity > 1 && (
                          <small>{plural(slot.seats_left, 'место', 'места', 'мест')}</small>
                        )}
                      </button>
                    ))}
                </div>
              </div>
            ))}
        </Section>
      )}
      {opened && (
        <BookingDetails booking={opened} onBack={() => setOpened(null)} onChanged={reload} />
      )}
      {booking && (
        <BookClient
          slot={booking}
          serviceName={serviceName(booking.service_id)}
          timezone={timezone}
          onBack={() => setBooking(null)}
          onBooked={reload}
        />
      )}
    </>
  )
}
