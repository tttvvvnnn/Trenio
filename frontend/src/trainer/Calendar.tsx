import { useEffect, useState } from 'react'

import {
  fetchPendingBookings,
  fetchServices,
  fetchSlots,
  fetchTrainerBookings,
  fetchUnmarkedBookings,
  type Booking,
  type Service,
  type Slot,
} from '../api'
import { bookingNote, dayTitle, duration, fullName, localDate, localTime, plural } from '../format'
import { haptic } from '../telegram'
import { monthDays, nextBooking } from '../calendar'
import { DateLeaf, Named } from '../ui/BookingDays'
import MonthCalendar, { BookingBadge } from '../ui/MonthCalendar'
import { PersonAvatar } from '../ui/Avatar'
import NextSession from '../ui/NextSession'
import Screen from '../ui/Screen'
import { AddRow, EmptyState, ErrorText, PageHeader, Row, Section, SkeletonList } from '../ui/kit'
import BookClient from './BookClient'
import BookingDetails from './BookingDetails'
import NewBooking from './NewBooking'

// Сколько неотмеченных занятий показываем сразу, остальные — по кнопке
const UNMARKED_PREVIEW = 3
// На сколько дней вперёд ищем ближайшее занятие для карточки наверху
const UPCOMING_DAYS = 14

type Props = {
  timezone: string
  onGoToSetup: () => void
}

type Data = {
  services: Service[]
  pending: Booking[]
  unmarked: Booking[]
  upcoming: Booking[]
}

function isActive(booking: Booking): boolean {
  return booking.status === 'pending' || booking.status === 'confirmed'
}

export default function Calendar({ timezone, onGoToSetup }: Props) {
  const today = localDate(new Date(), timezone)
  const [data, setData] = useState<Data | null>(null)
  const [month, setMonth] = useState(`${today.slice(0, 7)}-01`)
  // Записи показанного месяца; month — для какого месяца они загружены
  const [monthBookings, setMonthBookings] = useState<{ month: string; items: Booking[] } | null>(
    null,
  )
  const [slots, setSlots] = useState<{ day: string; items: Slot[] } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState(today)
  const [opened, setOpened] = useState<Booking | null>(null)
  const [booking, setBooking] = useState<Slot | null>(null)
  // Новая запись на выбранный день: в окошко или на любое время
  const [newBooking, setNewBooking] = useState(false)
  const [allUnmarked, setAllUnmarked] = useState(false)
  // Увеличиваем, чтобы перечитать данные после изменений
  const [reloads, setReloads] = useState(0)

  useEffect(() => {
    Promise.all([
      fetchServices(),
      fetchPendingBookings(),
      fetchUnmarkedBookings(),
      fetchTrainerBookings(UPCOMING_DAYS),
    ])
      .then(([services, pending, unmarked, upcoming]) =>
        setData({ services, pending, unmarked, upcoming }),
      )
      .catch((err: unknown) => setError(String(err)))
  }, [reloads])

  useEffect(() => {
    const days = monthDays(month)
    fetchTrainerBookings(days.length, days[0])
      .then((items) => setMonthBookings({ month, items }))
      .catch((err: unknown) => setError(String(err)))
  }, [month, reloads])

  useEffect(() => {
    // В прошлое не записывают: окошки нужны только с сегодняшнего дня
    if (selected < today) return
    fetchSlots(1, selected)
      .then((items) => setSlots({ day: selected, items }))
      .catch((err: unknown) => setError(String(err)))
  }, [selected, today, reloads])

  function reload() {
    setOpened(null)
    setAllUnmarked(false)
    setBooking(null)
    setNewBooking(false)
    setReloads((count) => count + 1)
  }

  function showMonth(next: string) {
    setMonth(next)
    // В новом месяце открываем сегодня, если оно там есть, иначе первое число
    setSelected(next.slice(0, 7) === today.slice(0, 7) ? today : next)
  }

  const header = <PageHeader title="Записи" brand />

  if (data === null) {
    return (
      <>
        {header}
        {error ? <ErrorText>{error}</ErrorText> : <SkeletonList rows={2} />}
      </>
    )
  }

  const { services, pending, unmarked, upcoming } = data
  if (services.length === 0) {
    return (
      <>
        {header}
        <EmptyState
          icon="calendar"
          title="Пока нет свободного времени"
          text="Добавьте услугу и рабочие часы, и окошки появятся здесь."
          action={{ label: 'Настроить расписание', onClick: onGoToSetup }}
        />
      </>
    )
  }

  const bookingsByDay = new Map<string, Booking[]>()
  // Отклонённые не показываем: они ничего не занимают и есть у клиента
  for (const item of monthBookings?.items.filter((b) => b.status !== 'declined') ?? []) {
    const day = localDate(item.starts_at, timezone)
    bookingsByDay.set(day, [...(bookingsByDay.get(day) ?? []), item])
  }
  const now = new Date()
  const next = nextBooking(upcoming, now)
  const daySlots = slots?.day === selected && selected >= today ? slots.items : []
  const dayBookings = bookingsByDay.get(selected) ?? []
  const loadingMonth = monthBookings?.month !== month
  const unmarkedRow = (item: Booking) => (
    <Row
      key={item.id}
      leading={<DateLeaf day={localDate(item.starts_at, timezone)} />}
      title={
        <Named
          avatar={<PersonAvatar person={item.client} size="xs" />}
          name={fullName(item.client)}
        />
      }
      subtitle={`${localTime(item.starts_at, timezone)} · ${bookingNote(item)}`}
      chevron
      onClick={() => setOpened(item)}
    />
  )
  const serviceName = (id: number) => services.find((service) => service.id === id)?.name ?? ''

  return (
    <>
      {header}
      {error && <ErrorText>{error}</ErrorText>}
      {next && (
        <NextSession
          booking={next}
          viewer="trainer"
          timezone={timezone}
          now={now}
          together={upcoming.filter(
            (item) =>
              isActive(item) &&
              item.starts_at === next.starts_at &&
              item.service.id === next.service.id,
          )}
          onOpen={() => setOpened(next)}
        />
      )}
      {pending.length > 0 && (
        <Section title="Ждут подтверждения">
          {pending.map((item) => (
            <Row
              key={item.id}
              leading={<DateLeaf day={localDate(item.starts_at, timezone)} />}
              title={
                <Named
                  avatar={<PersonAvatar person={item.client} size="xs" />}
                  name={fullName(item.client)}
                />
              }
              subtitle={`${localTime(item.starts_at, timezone)} · ${item.service.name}`}
              chevron
              onClick={() => setOpened(item)}
            />
          ))}
        </Section>
      )}
      {unmarked.length > 0 && (
        <Section
          title={`Не отмечены · ${unmarked.length}`}
          footer="Отметьте, прошло ли занятие: так оно спишется из блока клиента."
        >
          {unmarked.slice(0, UNMARKED_PREVIEW).map(unmarkedRow)}
          {unmarked.length > UNMARKED_PREVIEW && (
            <Row
              title={`Все неотмеченные · ${unmarked.length}`}
              tone="accent"
              chevron
              onClick={() => setAllUnmarked(true)}
            />
          )}
        </Section>
      )}
      <MonthCalendar
        month={month}
        today={today}
        selected={selected}
        timezone={timezone}
        bookings={bookingsByDay}
        loading={loadingMonth}
        onMonth={showMonth}
        onSelect={setSelected}
      />
      <h2 className="section-title day-title">{dayTitle(selected)}</h2>
      {!loadingMonth && dayBookings.length === 0 && daySlots.length === 0 && (
        <p className="section-footer">В этот день нет записей и свободного времени.</p>
      )}
      {dayBookings.length > 0 && (
        <div className="group">
          {dayBookings.map((item) => (
            <Row
              key={item.id}
              title={`${localTime(item.starts_at, timezone)} · ${fullName(item.client)}`}
              subtitle={bookingNote(item, now)}
              leading={<PersonAvatar person={item.client} />}
              tone={isActive(item) || item.attendance ? undefined : 'muted'}
              onClick={() => setOpened(item)}
              badge={<BookingBadge booking={item} now={now} />}
            />
          ))}
        </div>
      )}
      {selected >= today && (
        <div className="group">
          <AddRow title="Записать клиента" onClick={() => setNewBooking(true)} />
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
      {allUnmarked && (
        <Screen title="Не отмечены" onBack={() => setAllUnmarked(false)}>
          <Section>{unmarked.map(unmarkedRow)}</Section>
        </Screen>
      )}
      {opened && (
        <BookingDetails booking={opened} onBack={() => setOpened(null)} onChanged={reload} />
      )}
      {newBooking && (
        <NewBooking
          timezone={timezone}
          day={selected}
          onBack={() => setNewBooking(false)}
          onBooked={reload}
        />
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
