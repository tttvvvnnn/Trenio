import { useEffect, useState } from 'react'

import {
  cancelMyBooking,
  fetchMyBookings,
  fetchTrainerSlots,
  rescheduleMyBooking,
  type Booking,
} from '../api'
import { dateTime, duration, rescheduleNote } from '../format'
import CancelScreen from '../ui/CancelScreen'
import { EmptyState, ErrorText, PageHeader, Row, Section, SkeletonList } from '../ui/kit'
import ReminderSettings from '../ui/ReminderSettings'
import RescheduleScreen from '../ui/RescheduleScreen'
import Screen from '../ui/Screen'
import StatusBadge from '../ui/StatusBadge'

type Props = {
  onBook: () => void
}

function isActive(booking: Booking): boolean {
  return booking.status === 'pending' || booking.status === 'confirmed'
}

export default function MyBookings({ onBook }: Props) {
  const [bookings, setBookings] = useState<Booking[] | null>(null)
  const [opened, setOpened] = useState<Booking | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchMyBookings()
      .then(setBookings)
      .catch((err: unknown) => setError(String(err)))
  }, [])

  function replace(updated: Booking) {
    // После переноса запись могла переехать в списке: сортируем по времени заново
    setBookings(
      (current) =>
        current
          ?.map((item) => (item.id === updated.id ? updated : item))
          .sort((a, b) => Date.parse(a.starts_at) - Date.parse(b.starts_at)) ?? null,
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
      {bookings !== null && <ReminderSettings role="client" />}
      {opened && (
        <BookingDetails
          booking={opened}
          onBack={() => setOpened(null)}
          onChanged={(updated) => {
            replace(updated)
            setOpened(updated)
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
      subtitle={[
        booking.service.name,
        booking.trainer.display_name,
        isActive(booking) && booking.rescheduled_from ? 'перенесена' : null,
      ]
        .filter(Boolean)
        .join(' · ')}
      tone={isActive(booking) ? undefined : 'muted'}
      onClick={onClick}
      badge={<StatusBadge status={booking.status} />}
    />
  )
}

type DetailsProps = {
  booking: Booking
  onBack: () => void
  onChanged: (booking: Booking) => void
}

function BookingDetails({ booking, onBack, onChanged }: DetailsProps) {
  // Открытый поверх экран: отмена или перенос
  const [step, setStep] = useState<'cancel' | 'reschedule' | null>(null)
  const timezone = booking.trainer.timezone

  let note: string | null = null
  if (booking.status === 'pending') {
    note = 'Тренер ещё не подтвердил запись.'
  } else if (booking.status === 'declined') {
    note = 'Тренер не смог принять запись. Выберите другое время.'
  } else if (booking.status === 'cancelled') {
    note = booking.cancelled_by === 'trainer' ? 'Запись отменил тренер.' : 'Вы отменили запись.'
  } else if (booking.can_cancel) {
    note = `Отменить или перенести самому можно до ${dateTime(booking.cancel_deadline, timezone)}.`
  } else {
    note = 'Отменить или перенести самому уже нельзя. Если не получается прийти, напишите тренеру.'
  }
  const moved = rescheduleNote(booking, 'client')
  const inactive = !isActive(booking)
  // Без автоподтверждения перенос снова ждёт тренера; это видно по статусу после переноса
  const rescheduleFooter =
    'Необязательно. Тренер увидит комментарий и новое время в уведомлении. ' +
    'Если тренер подтверждает записи сам, перенос тоже будет ждать его подтверждения.'

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
        {moved && !inactive && (
          <Row
            title={moved}
            subtitle={booking.reschedule_comment ?? undefined}
            icon={{ name: 'clock', color: 'var(--c-accent)' }}
          />
        )}
        {inactive && booking.cancel_comment && (
          <Row title="Комментарий" subtitle={booking.cancel_comment} />
        )}
      </Section>
      {booking.can_cancel && (
        <Section>
          <Row title="Перенести" tone="accent" onClick={() => setStep('reschedule')} />
          <Row title="Отменить запись" tone="destructive" onClick={() => setStep('cancel')} />
        </Section>
      )}
      {step === 'cancel' && (
        <CancelScreen
          booking={booking}
          action="cancel"
          recipient="Тренер"
          onBack={() => setStep(null)}
          onSubmit={(comment) => cancelMyBooking(booking.id, comment)}
          onDone={(updated) => {
            setStep(null)
            onChanged(updated)
          }}
        />
      )}
      {step === 'reschedule' && (
        <RescheduleScreen
          booking={booking}
          loadSlots={(from, count) =>
            fetchTrainerSlots(booking.trainer.id, booking.service.id, count, from, booking.id)
          }
          allowCustom={false}
          footer={rescheduleFooter}
          onBack={() => setStep(null)}
          onSubmit={(startsAt, comment) => rescheduleMyBooking(booking.id, startsAt, comment)}
          onDone={(updated) => {
            setStep(null)
            onChanged(updated)
          }}
        />
      )}
    </Screen>
  )
}
