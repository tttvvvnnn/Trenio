import { useState, type ReactNode } from 'react'

import {
  errorText,
  changeTrainerBooking,
  fetchSlots,
  markAttendance,
  rescheduleTrainerBooking,
  type Attendance,
  type Booking,
  type BookingAction,
} from '../api'
import {
  ATTENDANCE,
  ATTENDANCE_SHORT,
  bookingMinutes,
  dayTitle,
  duration,
  fullName,
  localDate,
  localTime,
  rescheduleNote,
  rubles,
} from '../format'
import { haptic } from '../telegram'
import CancelScreen from '../ui/CancelScreen'
import RescheduleScreen from '../ui/RescheduleScreen'
import { PersonAvatar } from '../ui/Avatar'
import { ErrorText, Row, Section } from '../ui/kit'
import Screen from '../ui/Screen'
import StatusBadge from '../ui/StatusBadge'
import { withUndo } from '../undo'
import BookingTerms from './BookingTerms'
import NoteForm from './NoteForm'

type Props = {
  booking: Booking
  onBack: () => void
  onChanged: (booking: Booking) => void
}

/** Запись глазами тренера: сводка сверху, отметка посещения, действия, заметка и условия. */
export default function BookingDetails({ booking, onBack, onChanged }: Props) {
  const [busy, setBusy] = useState<BookingAction | 'mark' | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Открытый поверх экран: отмена, отклонение или перенос
  const [step, setStep] = useState<'cancel' | 'decline' | 'reschedule' | 'terms' | 'note' | null>(
    null,
  )
  const { client } = booking
  const timezone = booking.trainer.timezone

  async function act(action: BookingAction) {
    setBusy(action)
    setError(null)
    try {
      const updated = await changeTrainerBooking(booking.id, action)
      haptic.success()
      onChanged(updated)
    } catch (err) {
      haptic.error()
      setError(errorText(err))
    } finally {
      setBusy(null)
    }
  }

  // Нажатие на выбранную отметку снимает её. После отметки 5 секунд можно вернуть прежнюю
  async function mark(pressed: Attendance) {
    if (busy) return
    const previous = booking.attendance
    const next = pressed === previous ? null : pressed
    setBusy('mark')
    setError(null)
    try {
      const updated = await markAttendance(booking.id, next)
      haptic.success()
      onChanged(updated)
      withUndo({
        text: next ? `Отмечено: ${ATTENDANCE_SHORT[next]}` : 'Отметка снята',
        undo: () => markAttendance(booking.id, previous).then(onChanged),
      })
    } catch (err) {
      haptic.error()
      setError(errorText(err))
    } finally {
      setBusy(null)
    }
  }

  const pending = booking.status === 'pending'
  const marks: Attendance[] =
    booking.status === 'cancelled'
      ? ['missed_charged', 'missed_free']
      : ['attended', 'missed_charged', 'missed_free']
  let note: string | null = null
  if (pending) note = 'Клиент ждёт ответа. Пока запись не отклонена, время занято.'
  else if (booking.status === 'cancelled')
    note = booking.cancelled_by === 'client' ? 'Клиент отменил запись.' : 'Вы отменили запись.'
  else if (booking.status === 'declined') note = 'Вы отклонили запись.'
  else if (booking.created_by === 'trainer') note = 'Вы записали клиента сами.'
  const moved = rescheduleNote(booking, 'trainer')
  const inactive = booking.status === 'cancelled' || booking.status === 'declined'
  const comment = inactive ? booking.cancel_comment : null
  const name = fullName(client)
  const day = dayTitle(localDate(booking.starts_at, timezone))
  const time = `${localTime(booking.starts_at, timezone)}–${localTime(booking.ends_at, timezone)}`
  const where = [booking.service.name, booking.address].filter(Boolean).join(' · ')

  return (
    <Screen
      title={name}
      onBack={onBack}
      header={
        <div className="booking-head">
          <PersonAvatar person={client} size="md" />
          <div>
            <h1>{name}</h1>
            <p>
              {day} · {time}
            </p>
            <p>{where}</p>
            {client.username && <p>@{client.username}</p>}
            <StatusBadge status={booking.status} />
          </div>
        </div>
      }
    >
      {note && <p className="section-footer">{note}</p>}
      {((moved && !inactive) || comment) && (
        <Section>
          {moved && !inactive && (
            <Row
              title={moved}
              subtitle={booking.reschedule_comment ?? undefined}
              icon={{ name: 'clock', color: 'var(--c-accent)' }}
            />
          )}
          {comment && <Row title="Комментарий" subtitle={comment} />}
        </Section>
      )}
      {booking.can_mark && (
        <Section title="Как прошло" footer={chargeNote(booking)}>
          <div className="attendance" role="group" aria-label="Посещение">
            {marks.map((attendance) => (
              <button
                key={attendance}
                type="button"
                aria-pressed={booking.attendance === attendance}
                disabled={busy !== null}
                onClick={() => void mark(attendance)}
              >
                {ATTENDANCE[attendance]}
              </button>
            ))}
          </div>
        </Section>
      )}
      {pending && (
        <Section>
          <Row
            title={busy === 'confirm' ? 'Подтверждаем…' : 'Подтвердить'}
            tone="accent"
            centered
            onClick={busy ? undefined : () => void act('confirm')}
          />
          {booking.can_cancel && (
            <Row
              title="Отклонить"
              tone="destructive"
              centered
              onClick={busy ? undefined : () => setStep('decline')}
            />
          )}
        </Section>
      )}
      {!pending && booking.can_cancel && (
        <Section>
          <Row
            title="Перенести"
            tone="accent"
            centered
            onClick={busy ? undefined : () => setStep('reschedule')}
          />
          <Row
            title="Отменить запись"
            tone="destructive"
            centered
            onClick={busy ? undefined : () => setStep('cancel')}
          />
        </Section>
      )}
      {error && <ErrorText>{error}</ErrorText>}
      <Section title="Заметка">
        <Row
          title={booking.note ?? 'Добавить заметку'}
          subtitle={
            booking.note
              ? booking.note_private
                ? 'Видите только вы'
                : 'Клиент тоже видит'
              : undefined
          }
          tone={booking.note ? undefined : 'accent'}
          icon={{ name: 'note', color: 'var(--c-violet)' }}
          chevron
          onClick={busy ? undefined : () => setStep('note')}
        />
      </Section>
      <Section footer={booking.can_mark ? undefined : blockNote(booking)}>
        <Row
          title="Условия занятия"
          subtitle={termsLine(booking)}
          chevron
          onClick={busy ? undefined : () => setStep('terms')}
        />
      </Section>
      {(step === 'cancel' || step === 'decline') && (
        <CancelScreen
          booking={booking}
          action={step}
          recipient="Клиент"
          onBack={() => setStep(null)}
          onSubmit={(text) => changeTrainerBooking(booking.id, step, text)}
          onDone={(updated) => {
            setStep(null)
            onChanged(updated)
          }}
        />
      )}
      {step === 'reschedule' && (
        <RescheduleScreen
          booking={booking}
          loadSlots={(from, count) => fetchSlots(count, from, booking.service.id, booking.id)}
          allowCustom
          footer="Необязательно. Запись останется подтверждённой, клиенту придёт уведомление с новым временем."
          onBack={() => setStep(null)}
          onSubmit={(startsAt, text) => rescheduleTrainerBooking(booking.id, startsAt, text)}
          onDone={(updated) => {
            setStep(null)
            onChanged(updated)
          }}
        />
      )}
      {step === 'note' && (
        <NoteForm
          booking={booking}
          onBack={() => setStep(null)}
          onSaved={(updated) => {
            setStep(null)
            onChanged(updated)
          }}
        />
      )}
      {step === 'terms' && (
        <BookingTerms
          booking={booking}
          onBack={() => setStep(null)}
          onSaved={(updated) => {
            setStep(null)
            onChanged(updated)
          }}
        />
      )}
    </Screen>
  )
}

// Будущее занятие: из какого блока спишется или почему без блока
function blockNote(booking: Booking): ReactNode {
  if (booking.no_package) return 'Не списывается из блока: разовое занятие, оплата отдельно.'
  if (booking.out_of_block) {
    return (
      <span className="hint-alert">
        Без блока: подходящего блока нет или его занятия уже заняты более ранними записями. Занятие
        будет разовым, если не продать клиенту новый блок.
      </span>
    )
  }
  if (booking.one_off) return 'У клиента нет блоков: занятие разовое.'
  if (booking.planned) {
    const { package_name, number, sessions_count } = booking.planned
    return `Спишется из блока «${package_name}»: занятие ${number} из ${sessions_count}.`
  }
  return undefined
}

// Что особенного в условиях: своя длительность, цена разового, не из блока
function termsLine(booking: Booking): string {
  const parts = []
  if (bookingMinutes(booking) !== booking.service.duration_min) {
    parts.push(`своя длительность ${duration(bookingMinutes(booking))}`)
  }
  if (booking.no_package) parts.push('не из блока')
  if (booking.price !== null && (booking.one_off || booking.no_package)) {
    parts.push(`разовое ${rubles(booking.price)}`)
  }
  return parts.length > 0 ? parts.join(' · ') : 'Как у услуги'
}

function chargeNote(booking: Booking): string {
  if (booking.no_package && !booking.charge && booking.attendance !== 'missed_free') {
    return 'Не списывается из блока: разовое занятие, оплата отдельно.'
  }
  if (booking.charge) {
    const { package_name, number, sessions_count } = booking.charge
    return `Списано из блока «${package_name}»: занятие ${number} из ${sessions_count}.`
  }
  if (booking.attendance === 'missed_free') return 'Пропуск без списания: блок не тратится.'
  if (booking.one_off) {
    return booking.attendance
      ? 'Разовое занятие: подходящего блока нет, оплата отдельно.'
      : 'Подходящего блока нет: после отметки занятие станет разовым.'
  }
  if (booking.attendance === null) {
    return '«Прошла» и «Пропуск, списать» спишут занятие из самого старого подходящего блока.'
  }
  return ''
}
