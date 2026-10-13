import { useEffect, useState } from 'react'

import { cancelMyBooking, fetchMyBookings, type Booking } from '../api'
import { dateTime, duration } from '../format'
import { confirmAction, haptic } from '../telegram'
import { EmptyState, ErrorText, PageHeader, Row, Section, SkeletonList } from '../ui/kit'
import Screen from '../ui/Screen'
import StatusBadge from '../ui/StatusBadge'

type Props = {
  onBook: () => void
  // Есть, когда человек ещё и тренер: возврат к своему расписанию
  onSwitchToTrainer?: () => void
}

function isActive(booking: Booking): boolean {
  return booking.status === 'pending' || booking.status === 'confirmed'
}

export default function MyBookings({ onBook, onSwitchToTrainer }: Props) {
  const [bookings, setBookings] = useState<Booking[] | null>(null)
  const [opened, setOpened] = useState<Booking | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchMyBookings()
      .then(setBookings)
      .catch((err: unknown) => setError(String(err)))
  }, [])

  function replace(updated: Booking) {
    setBookings(
      (current) => current?.map((item) => (item.id === updated.id ? updated : item)) ?? null,
    )
  }

  const active = bookings?.filter(isActive) ?? []
  const inactive = bookings?.filter((booking) => !isActive(booking)) ?? []

  return (
    <>
      <PageHeader title="Мои записи" />
      {bookings === null && !error && <SkeletonList rows={2} />}
      {error && <ErrorText>{error}</ErrorText>}
      {bookings !== null && active.length === 0 && (
        <EmptyState
          icon="calendar"
          title="Записей пока нет"
          text="Выберите свободное время у тренера, и запись появится здесь."
          action={{ label: 'Записаться', onClick: onBook }}
        />
      )}
      {active.length > 0 && (
        <Section title="Предстоящие">
          {active.map((booking) => (
            <BookingRow key={booking.id} booking={booking} onClick={() => setOpened(booking)} />
          ))}
        </Section>
      )}
      {inactive.length > 0 && (
        <Section title="Отменённые">
          {inactive.map((booking) => (
            <BookingRow key={booking.id} booking={booking} onClick={() => setOpened(booking)} />
          ))}
        </Section>
      )}
      {onSwitchToTrainer && (
        <Section footer="Ваше расписание и клиенты остаются в режиме тренера.">
          <Row
            title="Режим тренера"
            icon={{ name: 'user', color: 'var(--c-violet)' }}
            chevron
            onClick={onSwitchToTrainer}
          />
        </Section>
      )}
      {opened && (
        <BookingDetails
          booking={opened}
          onBack={() => setOpened(null)}
          onChanged={(updated) => {
            replace(updated)
            setOpened(null)
          }}
        />
      )}
    </>
  )
}

function BookingRow({ booking, onClick }: { booking: Booking; onClick: () => void }) {
  return (
    <Row
      title={dateTime(booking.starts_at, booking.trainer.timezone)}
      subtitle={`${booking.service.name} · ${booking.trainer.display_name}`}
      tone={isActive(booking) ? undefined : 'muted'}
      onClick={onClick}
      after={<StatusBadge status={booking.status} />}
    />
  )
}

type DetailsProps = {
  booking: Booking
  onBack: () => void
  onChanged: (booking: Booking) => void
}

function BookingDetails({ booking, onBack, onChanged }: DetailsProps) {
  const [cancelling, setCancelling] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const timezone = booking.trainer.timezone

  async function cancel() {
    const ok = await confirmAction('Отменить запись? Время освободится для других.', 'Отменить')
    if (!ok) return
    setCancelling(true)
    setError(null)
    try {
      const updated = await cancelMyBooking(booking.id)
      haptic.success()
      onChanged(updated)
    } catch (err) {
      haptic.error()
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setCancelling(false)
    }
  }

  let note: string | null = null
  if (booking.status === 'pending') {
    note = 'Тренер ещё не подтвердил запись.'
  } else if (booking.status === 'declined') {
    note = 'Тренер не смог принять запись. Выберите другое время.'
  } else if (booking.status === 'cancelled') {
    note = booking.cancelled_by === 'trainer' ? 'Запись отменил тренер.' : 'Вы отменили запись.'
  } else if (booking.can_cancel) {
    note = `Отменить самому можно до ${dateTime(booking.cancel_deadline, timezone)}.`
  } else {
    note = 'Отменить самому уже нельзя. Если не получается прийти, напишите тренеру.'
  }

  return (
    <Screen
      title={booking.service.name}
      subtitle={dateTime(booking.starts_at, timezone)}
      onBack={onBack}
    >
      <Section footer={note}>
        <Row title="Статус" after={<StatusBadge status={booking.status} />} />
        <Row title="Тренер" value={booking.trainer.display_name} />
        <Row title="Длительность" value={duration(booking.service.duration_min)} />
        {booking.address && <Row title="Место" subtitle={booking.address} />}
      </Section>
      {error && <ErrorText>{error}</ErrorText>}
      {booking.can_cancel && (
        <Section>
          <Row
            title={cancelling ? 'Отменяем…' : 'Отменить запись'}
            tone="destructive"
            onClick={cancelling ? undefined : () => void cancel()}
          />
        </Section>
      )}
    </Screen>
  )
}
