import { useRef, type ReactNode } from 'react'

import { monthDays, shiftMonth } from '../calendar'
import { WEEKDAYS_SHORT, dayOfMonth, monthTitle } from '../format'
import { haptic } from '../telegram'
import Icon from './icons'

// Насколько нужно провести пальцем, чтобы листнуть месяц
const SWIPE_PX = 50

type Props = {
  // Первое число показанного месяца
  month: string
  today: string
  isSelected: (day: string) => boolean
  loading: boolean
  onMonth: (month: string) => void
  onSelect: (day: string) => void
  // Что показать в клетке под числом
  renderDay?: (day: string) => ReactNode
  // Дополнительные классы клетки: например, «нет окошек»
  dayClass?: (day: string) => string | undefined
  // Подпись для экранных читалок
  dayLabel?: (day: string) => string
  // Клетки ниже ростом, когда в них только точки
  compact?: boolean
  legend?: ReactNode
}

/** Сетка месяца с листанием стрелками и свайпом. Содержимое клеток задаёт экран. */
export default function MonthGrid({
  month,
  today,
  isSelected,
  loading,
  onMonth,
  onSelect,
  renderDay,
  dayClass,
  dayLabel,
  compact,
  legend,
}: Props) {
  const touch = useRef<{ x: number; y: number } | null>(null)
  const days = monthDays(month)

  function go(by: number) {
    haptic.select()
    onMonth(shiftMonth(month, by))
  }

  const gridClass = ['group', 'month-grid', compact && 'compact', loading && 'loading']
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
        className={gridClass.filter(Boolean).join(' ')}
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
          const selected = isSelected(day)
          const classes = [
            'month-day',
            day.slice(0, 7) !== month.slice(0, 7) && 'outside',
            day === today && 'today',
            selected && 'selected',
            dayClass?.(day),
          ]
          return (
            <button
              key={day}
              type="button"
              className={classes.filter(Boolean).join(' ')}
              aria-label={dayLabel?.(day)}
              aria-pressed={selected}
              onClick={() => {
                haptic.select()
                onSelect(day)
              }}
            >
              <span className="month-number">{dayOfMonth(day)}</span>
              {renderDay?.(day)}
            </button>
          )
        })}
      </div>
      {legend && <div className="month-legend">{legend}</div>}
    </section>
  )
}
