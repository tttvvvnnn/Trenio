import { useState } from 'react'

import {
  changeTrainerBooking,
  markAttendance,
  type Attendance,
  type Booking,
  type BookingAction,
} from '../api'
import { ATTENDANCE, dateTime, duration, fullName } from '../format'
import { confirmAction, haptic } from '../telegram'
import Icon from '../ui/icons'
import { ErrorText, Row, Section } from '../ui/kit'
import { MainButton } from '../ui/native'
import Screen from '../ui/Screen'
import StatusBadge from '../ui/StatusBadge'

type Props = {
  booking: Booking
  onBack: () => void
  onChanged: (booking: Booking) => void
}

/** Запись глазами тренера: кто, когда, и что с ней сделать. */
export default function BookingDetails({ booking, onBack, onChanged }: Props) {
  const [busy, setBusy] = useState<BookingAction | 'mark' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { client } = booking
  const timezone = booking.trainer.timezone

  async function act(action: BookingAction) {
    if (action === 'cancel') {
      const ok = await confirmAction(
        'Отменить запись? Время освободится, клиент увидит отмену в приложении.',
        'Отменить',
      )
      if (!ok) return
    }
    setBusy(action)
    setError(null)
    try {
      const updated = await changeTrainerBooking(booking.id, action)
      haptic.success()
      onChanged(updated)
    } catch (err) {
      haptic.error()
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(null)
    }
  }

  async function mark(attendance: Attendance | null) {
    if (attendance === booking.attendance) return
    setBusy('mark')
    setError(null)
    try {
      const updated = await markAttendance(booking.id, attendance)
      haptic.success()
      onChanged(updated)
    } catch (err) {
      haptic.error()
      setError(err instanceof Error ? err.message : String(err))
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
  else if (booking.created_by === 'trainer') note = 'Вы записали клиента сами.'

  return (
    <Screen
      title={fullName(client)}
      subtitle={client.username ? `@${client.username}` : undefined}
      onBack={onBack}
    >
      <Section footer={note}>
        <Row title="Статус" after={<StatusBadge status={booking.status} />} />
        <Row title="Когда" subtitle={dateTime(booking.starts_at, timezone)} />
        <Row
          title="Услуга"
          value={`${booking.service.name}, ${duration(booking.service.duration_min)}`}
        />
        {booking.address && <Row title="Место" subtitle={booking.address} />}
      </Section>
      {booking.can_mark && (
        <Section title="Посещение" footer={chargeNote(booking)}>
          {marks.map((attendance) => (
            <Row
              key={attendance}
              title={ATTENDANCE[attendance]}
              onClick={busy ? undefined : () => void mark(attendance)}
              after={
                booking.attendance === attendance ? (
                  <Icon name="check" className="row-check" />
                ) : undefined
              }
            />
          ))}
          {booking.attendance && (
            <Row
              title={busy === 'mark' ? 'Сохраняем…' : 'Снять отметку'}
              tone="accent"
              onClick={busy ? undefined : () => void mark(null)}
            />
          )}
        </Section>
      )}
      {!booking.can_mark && booking.one_off && !booking.out_of_block && (
        <p className="section-footer">У клиента нет блоков: занятие разовое.</p>
      )}
      {!booking.can_mark && booking.out_of_block && (
        <p className="section-footer hint-alert">
          Без блока: подходящего блока нет или его занятия уже заняты более ранними записями.
          Занятие будет разовым, если не продать клиенту новый блок.
        </p>
      )}
      {!booking.can_mark && booking.planned && (
        <p className="section-footer">
          Спишется из блока «{booking.planned.package_name}»: занятие {booking.planned.number} из{' '}
          {booking.planned.sessions_count}.
        </p>
      )}
      {error && <ErrorText>{error}</ErrorText>}
      {pending && (
        <Section>
          <Row
            title={busy === 'decline' ? 'Отклоняем…' : 'Отклонить'}
            tone="destructive"
            onClick={busy ? undefined : () => void act('decline')}
          />
        </Section>
      )}
      {!pending && booking.can_cancel && (
        <Section>
          <Row
            title={busy === 'cancel' ? 'Отменяем…' : 'Отменить запись'}
            tone="destructive"
            onClick={busy ? undefined : () => void act('cancel')}
          />
        </Section>
      )}
      <MainButton
        text="Подтвердить запись"
        onClick={() => void act('confirm')}
        visible={pending}
        disabled={busy !== null && busy !== 'confirm'}
        loading={busy === 'confirm'}
      />
    </Screen>
  )
}

function chargeNote(booking: Booking): string {
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
