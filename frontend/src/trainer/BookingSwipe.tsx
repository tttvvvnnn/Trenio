import { useState, type ReactNode } from 'react'

import {
  changeTrainerBooking,
  errorText,
  fetchSlots,
  markAttendance,
  rescheduleTrainerBooking,
  type Attendance,
  type Booking,
} from '../api'
import { ATTENDANCE_SHORT } from '../format'
import { chooseAction, haptic } from '../telegram'
import CancelScreen from '../ui/CancelScreen'
import RescheduleScreen from '../ui/RescheduleScreen'
import SwipeRow, { type SwipeAction } from '../ui/Swipe'
import { withUndo } from '../undo'

type Props = {
  booking: Booking
  onChanged: (booking: Booking) => void
  onError?: (message: string) => void
  children: ReactNode
}

/**
 * Свайп влево по записи: прошедшую — отметить, будущую — перенести или отменить,
 * заявку — подтвердить или отклонить. Нажатие по строке по-прежнему открывает запись.
 */
export default function BookingSwipe({ booking, onChanged, onError, children }: Props) {
  const [screen, setScreen] = useState<'cancel' | 'decline' | 'reschedule' | null>(null)

  async function run(action: () => Promise<Booking>) {
    try {
      const updated = await action()
      haptic.success()
      onChanged(updated)
      return true
    } catch (err) {
      haptic.error()
      onError?.(errorText(err))
      return false
    }
  }

  async function mark(attendance: Attendance) {
    const previous = booking.attendance
    const ok = await run(() => markAttendance(booking.id, attendance))
    if (!ok) return
    withUndo({
      text: `Отмечено: ${ATTENDANCE_SHORT[attendance]}`,
      undo: () => markAttendance(booking.id, previous).then(onChanged),
    })
  }

  async function missed() {
    const choice = await chooseAction('Пропуск. Списать занятие из блока?', [
      ['missed_charged', 'Списать'],
      ['missed_free', 'Не списывать'],
    ])
    if (choice) await mark(choice)
  }

  let actions: SwipeAction[] = []
  let full: (() => void) | undefined
  if (booking.can_mark) {
    actions = [
      { label: 'Пропуск', tone: 'muted', onClick: () => void missed() },
      { label: 'Пришёл', tone: 'success', onClick: () => void mark('attended') },
    ]
    if (booking.status !== 'cancelled') full = () => void mark('attended')
    else actions = actions.slice(0, 1)
  } else if (booking.status === 'pending' && booking.can_cancel) {
    actions = [
      { label: 'Отклонить', tone: 'destructive', onClick: () => setScreen('decline') },
      {
        label: 'Подтвердить',
        tone: 'success',
        onClick: () => void run(() => changeTrainerBooking(booking.id, 'confirm')),
      },
    ]
  } else if (booking.can_cancel) {
    actions = [
      { label: 'Перенести', tone: 'planned', onClick: () => setScreen('reschedule') },
      { label: 'Отменить', tone: 'destructive', onClick: () => setScreen('cancel') },
    ]
  }

  if (actions.length === 0) return children

  return (
    <>
      <SwipeRow actions={actions} onFullSwipe={full}>
        {children}
      </SwipeRow>
      {(screen === 'cancel' || screen === 'decline') && (
        <CancelScreen
          booking={booking}
          action={screen}
          recipient="Клиент"
          onBack={() => setScreen(null)}
          onSubmit={(text) => changeTrainerBooking(booking.id, screen, text)}
          onDone={(updated) => {
            setScreen(null)
            onChanged(updated)
          }}
        />
      )}
      {screen === 'reschedule' && (
        <RescheduleScreen
          booking={booking}
          loadSlots={(from, count) => fetchSlots(count, from, booking.service.id, booking.id)}
          allowCustom
          footer="Необязательно. Запись останется подтверждённой, клиенту придёт уведомление с новым временем."
          onBack={() => setScreen(null)}
          onSubmit={(startsAt, text) => rescheduleTrainerBooking(booking.id, startsAt, text)}
          onDone={(updated) => {
            setScreen(null)
            onChanged(updated)
          }}
        />
      )}
    </>
  )
}
