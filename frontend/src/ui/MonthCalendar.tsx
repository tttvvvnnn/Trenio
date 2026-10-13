import { useRef } from 'react'

import type { Booking } from '../api'
import { TONE_LABEL, bookingTone, monthDays, shiftMonth } from '../calendar'
import { WEEKDAYS_SHORT, dayOfMonth, fullName, localTime, monthTitle } from '../format'
import { haptic } from '../telegram'
import Icon from './icons'

// Сколько записей помещается в клетку дня, остальные — «+N»
const CHIPS_PER_DAY = 2
// Насколько нужно провести пальцем, чтобы листнуть месяц
const SWIPE_PX = 50

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

/** Календарь на месяц: в клетке дня — время и имя клиента, цвет — состояние записи. */
export default function MonthCalendar({
  month,
  today,
  selected,
  timezone,
  bookings,
  loading,
  onMonth,
  onSelect,
}: Props) {
  const touch = useRef<{ x: number; y: number } | null>(null)
  const now = new Date()
  const days = monthDays(month)

  function go(by: number) {
    haptic.select()
    onMonth(shiftMonth(month, by))
  }

  return (
    <section className="section month">
      <div className="month-head">
        <button
          type="button"
          className="month-arrow"
          aria-label="Прошлый месяц"
          onClick={() => go(-1)}
        >
          <Icon name="chevronLeft" />
        </button>
        <h2>{monthTitle(month)}</h2>
        <button
          type="button"
          className="month-arrow"
          aria-label="Следующий месяц"
          onClick={() => go(1)}
        >
          <Icon name="chevronRight" />
        </button>
      </div>
      <div
        className={loading ? 'group month-grid loading' : 'group month-grid'}
        onTouchStart={(event) => {
          const point = event.touches[0]
          touch.current = { x: point.clientX, y: point.clientY }
        }}
        onTouchEnd={(event) => {
          const start = touch.current
          touch.current = null
          if (!start) return
          const point = event.changedTouches[0]
          const dx = point.clientX - start.x
          if (Math.abs(dx) > SWIPE_PX && Math.abs(dx) > Math.abs(point.clientY - start.y)) {
            go(dx < 0 ? 1 : -1)
          }
        }}
      >
        {WEEKDAYS_SHORT.map((name) => (
          <span key={name} className="month-weekday">
            {name}
          </span>
        ))}
        {days.map((day) => {
          const own = (bookings.get(day) ?? []).filter(
            (b) => b.status === 'pending' || b.status === 'confirmed' || b.attendance !== null,
          )
          const classes = [
            'month-day',
            day.slice(0, 7) !== month.slice(0, 7) && 'outside',
            day === today && 'today',
            day === selected && 'selected',
          ]
          return (
            <button
              key={day}
              type="button"
              className={classes.filter(Boolean).join(' ')}
              aria-label={`${dayOfMonth(day)}, записей: ${own.length}`}
              aria-pressed={day === selected}
              onClick={() => {
                haptic.select()
                onSelect(day)
              }}
            >
              <span className="month-number">{dayOfMonth(day)}</span>
              {own.slice(0, CHIPS_PER_DAY).map((booking) => (
                <span key={booking.id} className={`month-chip ${bookingTone(booking, now)}`}>
                  <b>{localTime(booking.starts_at, timezone)}</b>
                  {fullName(booking.client)}
                </span>
              ))}
              {own.length > CHIPS_PER_DAY && (
                <span className="month-more">+{own.length - CHIPS_PER_DAY}</span>
              )}
            </button>
          )
        })}
      </div>
      <div className="month-legend">
        {(['planned', 'pending', 'alert', 'unmarked', 'done'] as const).map((tone) => (
          <span key={tone}>
            <i className={`month-dot ${tone}`} />
            {TONE_LABEL[tone]}
          </span>
        ))}
      </div>
    </section>
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
