import { Fragment, type ReactNode } from 'react'

import type { Booking } from '../api'
import { dayOfMonth, localDate, monthTitle, weekdayShort } from '../format'

/** Листок календаря слева в строке записи: «ср» и число. */
export function DateLeaf({ day, muted }: { day: string | null; muted?: boolean }) {
  // Вторая и следующие записи того же дня: место под листком пустое, чтобы текст не прыгал
  if (day === null) return <span className="date-leaf blank" aria-hidden="true" />
  return (
    <span className={muted ? 'date-leaf muted' : 'date-leaf'}>
      <span className="date-leaf-weekday">{weekdayShort(day)}</span>
      <span className="date-leaf-day">{dayOfMonth(day)}</span>
    </span>
  )
}

type Props = {
  bookings: Booking[]
  // Часовой пояс, в котором считаем дни; по умолчанию пояс тренера записи
  timezone?: string
  // Заголовок с месяцем над первым днём месяца: для длинной истории
  months?: boolean
  // leaf — листок для первой записи дня, null для остальных
  row: (booking: Booking, leaf: ReactNode) => ReactNode
}

/** Записи по дням: каждый день отдельной карточкой. */
export default function BookingDays({ bookings, timezone, months, row }: Props) {
  const days: { day: string; items: Booking[] }[] = []
  for (const booking of bookings) {
    const day = localDate(booking.starts_at, timezone ?? booking.trainer.timezone)
    const last = days[days.length - 1]
    if (last?.day === day) last.items.push(booking)
    else days.push({ day, items: [booking] })
  }

  return (
    <div className="booking-days">
      {days.map(({ day, items }, index) => {
        const month = monthTitle(day)
        const newMonth = months && (index === 0 || monthTitle(days[index - 1].day) !== month)
        return (
          <Fragment key={day}>
            {newMonth && <h2 className="section-title">{month}</h2>}
            <div className="group">
              {items.map((booking, position) =>
                row(
                  booking,
                  <DateLeaf
                    day={position === 0 ? day : null}
                    muted={!isActiveOrHappened(booking)}
                  />,
                ),
              )}
            </div>
          </Fragment>
        )
      })}
    </div>
  )
}

// Отменённые и отклонённые без отметки тренера — серым листком
function isActiveOrHappened(booking: Booking): boolean {
  return booking.status === 'pending' || booking.status === 'confirmed' || !!booking.attendance
}
