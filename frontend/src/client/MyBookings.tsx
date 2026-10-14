import { type ReactNode, useEffect, useState } from 'react'

import {
  cancelMyBooking,
  fetchMyBookings,
  fetchMyHistory,
  fetchTrainerSlots,
  rescheduleMyBooking,
  type Booking,
} from '../api'
import { dateTime, duration, localTime, rescheduleNote } from '../format'
import BookingDays, { Named } from '../ui/BookingDays'
import CancelScreen from '../ui/CancelScreen'
import { TrainerAvatar } from '../ui/Avatar'
import { EmptyState, ErrorText, PageHeader, Row, Section, Segmented, SkeletonList } from '../ui/kit'
import MyPhoto from '../ui/MyPhoto'
import ReminderSettings from '../ui/ReminderSettings'
import RescheduleScreen from '../ui/RescheduleScreen'
import Screen from '../ui/Screen'
import StatusBadge from '../ui/StatusBadge'

type Props = {
  onBook: () => void
}

type Tab = 'upcoming' | 'history'

// Столько записей сервер отдаёт за раз; страница короче — значит, история кончилась
const HISTORY_PAGE = 30

function isActive(booking: Booking): boolean {
  return booking.status === 'pending' || booking.status === 'confirmed'
}

export default function MyBookings({ onBook }: Props) {
  const [tab, setTab] = useState<Tab>('upcoming')
  const [bookings, setBookings] = useState<Booking[] | null>(null)
  // null — историю ещё не грузили или её надо перечитать
  const [history, setHistory] = useState<Booking[] | null>(null)
  const [historyEnd, setHistoryEnd] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [opened, setOpened] = useState<Booking | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchMyBookings()
      .then(setBookings)
      .catch((err: unknown) => setError(String(err)))
  }, [])

  useEffect(() => {
    if (tab !== 'history' || history !== null) return
    fetchMyHistory()
      .then((page) => {
        setHistory(page)
        setHistoryEnd(page.length < HISTORY_PAGE)
      })
      .catch((err: unknown) => setError(String(err)))
  }, [tab, history])

  async function loadMore() {
    if (!history?.length) return
    setLoadingMore(true)
    try {
      const page = await fetchMyHistory(history[history.length - 1].id)
      setHistory([...history, ...page])
      setHistoryEnd(page.length < HISTORY_PAGE)
    } catch (err) {
      setError(String(err))
    } finally {
      setLoadingMore(false)
    }
  }

  function replace(updated: Booking) {
    // После переноса запись могла переехать в списке: сортируем по времени заново
    setBookings(
      (current) =>
        current
          ?.map((item) => (item.id === updated.id ? updated : item))
          .sort((a, b) => Date.parse(a.starts_at) - Date.parse(b.starts_at)) ?? null,
    )
    // Отменённая запись уходит в историю: перечитаем её, когда откроют
    setHistory(null)
  }

  const active = bookings?.filter(isActive) ?? []
  // Имя тренера в истории нужно, только если тренеров несколько
  const manyTrainers = new Set(history?.map((booking) => booking.trainer.id)).size > 1

  return (
    <>
      <PageHeader title="Мои записи" />
      <Segmented
        label="Какие записи показать"
        value={tab}
        options={[
          ['upcoming', 'Предстоящие'],
          ['history', 'История'],
        ]}
        onChange={setTab}
      />
      {error && <ErrorText>{error}</ErrorText>}
      {tab === 'upcoming' && (
        <>
          {bookings === null && !error && <SkeletonList rows={2} />}
          {bookings !== null && active.length === 0 && (
            <EmptyState
              icon="calendar"
              title="Записей пока нет"
              text="Выберите свободное время у тренера, и запись появится здесь."
              action={{ label: 'Записаться', onClick: onBook }}
            />
          )}
          {active.length > 0 && (
            <BookingDays
              bookings={active}
              row={(booking, leaf) => (
                <UpcomingRow
                  key={booking.id}
                  booking={booking}
                  leaf={leaf}
                  onClick={() => setOpened(booking)}
                />
              )}
            />
          )}
          {bookings !== null && <MyPhoto variant="section" />}
          {bookings !== null && <ReminderSettings role="client" />}
        </>
      )}
      {tab === 'history' && (
        <>
          {history === null && !error && <SkeletonList rows={3} />}
          {history !== null && history.length === 0 && (
            <EmptyState
              icon="calendar"
              title="Прошедших записей пока нет"
              text="Здесь будут прошедшие и отменённые занятия."
            />
          )}
          {history !== null && history.length > 0 && (
            <BookingDays
              bookings={history}
              months
              row={(booking, leaf) => (
                <HistoryRow
                  key={booking.id}
                  booking={booking}
                  leaf={leaf}
                  withTrainer={manyTrainers}
                  onClick={() => setOpened(booking)}
                />
              )}
            />
          )}
          {history !== null && !historyEnd && (
            <button
              type="button"
              className="load-more"
              disabled={loadingMore}
              onClick={() => void loadMore()}
            >
              {loadingMore ? 'Загружаем…' : 'Показать ещё'}
            </button>
          )}
        </>
      )}
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

type RowProps = {
  booking: Booking
  leaf: ReactNode
  onClick: () => void
}

// "10:00–11:00 · (фото) Тихон · перенесена"
function UpcomingRow({ booking, leaf, onClick }: RowProps) {
  const timezone = booking.trainer.timezone
  return (
    <Row
      leading={leaf}
      title={booking.service.name}
      subtitle={
        <>
          {`${localTime(booking.starts_at, timezone)}–${localTime(booking.ends_at, timezone)} · `}
          <Named
            avatar={<TrainerAvatar trainer={booking.trainer} size="xs" />}
            name={booking.trainer.display_name}
          />
          {booking.rescheduled_from ? ' · перенесена' : null}
        </>
      }
      onClick={onClick}
      badge={
        booking.status === 'pending' ? (
          <span className="badge pending">ждёт</span>
        ) : (
          <span className="status-dot" role="img" aria-label="Подтверждена" />
        )
      }
    />
  )
}

// "10:00 · занятие 3 из 10" и итог занятия плашкой; тренер в конце, его не жалко обрезать
function HistoryRow({ booking, leaf, withTrainer, onClick }: RowProps & { withTrainer: boolean }) {
  const charge = booking.charge
  let detail: string | null = null
  if (charge) detail = `занятие ${charge.number} из ${charge.sessions_count}`
  else if (booking.one_off && booking.attendance) detail = 'разовая'
  else if (booking.status === 'cancelled')
    detail = booking.cancelled_by === 'trainer' ? 'отменил тренер' : 'вы отменили'
  return (
    <Row
      leading={leaf}
      title={booking.service.name}
      subtitle={[
        localTime(booking.starts_at, booking.trainer.timezone),
        detail,
        withTrainer ? booking.trainer.display_name : null,
      ]
        .filter(Boolean)
        .join(' · ')}
      tone={isActive(booking) || booking.attendance ? undefined : 'muted'}
      onClick={onClick}
      badge={<HistoryBadge booking={booking} />}
    />
  )
}

function HistoryBadge({ booking }: { booking: Booking }) {
  if (booking.attendance === 'attended') return <span className="badge success">прошла</span>
  if (booking.attendance === 'missed_charged') return <span className="badge alert">пропуск</span>
  if (booking.attendance === 'missed_free') return <span className="badge">пропуск</span>
  if (booking.status === 'cancelled') return <span className="badge">отменена</span>
  if (booking.status === 'declined') return <span className="badge">отклонена</span>
  return <span className="badge">не отмечена</span>
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
          <Row title="Перенести" tone="accent" centered onClick={() => setStep('reschedule')} />
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
