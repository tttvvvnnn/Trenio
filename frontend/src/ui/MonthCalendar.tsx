import type { Booking } from '../api'
import { TONE_LABEL, bookingTone } from '../calendar'
import { dayOfMonth, fullName, localTime } from '../format'
import MonthGrid from './MonthGrid'

// Сколько записей помещается в клетку дня, остальные — «+N»
const CHIPS_PER_DAY = 2

type Props = {
  // Первое число показанного месяца
  month: string
  today: string
  selected: string
  timezone: string
  // Записи по дням, YYYY-MM-DD → записи по времени
  bookings: Map<string, Booking[]>
  loading: boolean
  onMonth: (month: string) => void
  onSelect: (day: string) => void
}

/** Записи тренера на месяц: в клетке дня — время и имя клиента, цвет — состояние записи. */
export default function MonthCalendar({ selected, timezone, bookings, ...rest }: Props) {
  const now = new Date()
  const own = (day: string) =>
    (bookings.get(day) ?? []).filter(
      (b) => b.status === 'pending' || b.status === 'confirmed' || b.attendance !== null,
    )
  return (
    <MonthGrid
      {...rest}
      isSelected={(day) => day === selected}
      dayLabel={(day) => `${dayOfMonth(day)}, записей: ${own(day).length}`}
      renderDay={(day) => {
        const items = own(day)
        return (
          <>
            {items.slice(0, CHIPS_PER_DAY).map((booking) => (
              <span key={booking.id} className={`month-chip ${bookingTone(booking, now)}`}>
                <b>{localTime(booking.starts_at, timezone)}</b>
                {fullName(booking.client)}
              </span>
            ))}
            {items.length > CHIPS_PER_DAY && (
              <span className="month-more">+{items.length - CHIPS_PER_DAY}</span>
            )}
          </>
        )
      }}
      legend={(['planned', 'pending', 'alert', 'unmarked', 'done'] as const).map((tone) => (
        <span key={tone}>
          <i className={`month-dot ${tone}`} />
          {TONE_LABEL[tone]}
        </span>
      ))}
    />
  )
}

// Справа в строке записи: «без блока», ожидание ответа или отмена. Остальное — в подписи
export function BookingBadge({ booking, now }: { booking: Booking; now: Date }) {
  if (booking.status === 'cancelled' && !booking.attendance) {
    return <span className="badge">отменена</span>
  }
  const tone = bookingTone(booking, now)
  if (tone !== 'alert' && tone !== 'pending') return null
  return <span className={`badge ${tone}`}>{TONE_LABEL[tone]}</span>
}
