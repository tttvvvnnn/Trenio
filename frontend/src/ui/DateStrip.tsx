import { dayOfMonth, dayTitle, plural, weekdayShort } from '../format'
import { haptic } from '../telegram'

type Props = {
  // Дни YYYY-MM-DD по порядку
  days: string[]
  current: string
  // Сколько окошек в день; день без окошек рисуется бледным
  count: (day: string) => number
  onSelect: (day: string) => void
}

/** Лента дней с отметкой, есть ли в дне свободное время. */
export default function DateStrip({ days, current, count, onSelect }: Props) {
  return (
    <div className="date-strip" role="group" aria-label="Дни">
      {days.map((day) => {
        const slots = count(day)
        return (
          <button
            key={day}
            type="button"
            className={slots === 0 ? 'date empty' : 'date'}
            aria-pressed={day === current}
            aria-label={`${dayTitle(day)}, ${slots === 0 ? 'нет окошек' : plural(slots, 'окошко', 'окошка', 'окошек')}`}
            onClick={() => {
              haptic.select()
              onSelect(day)
            }}
          >
            <small>{weekdayShort(day)}</small>
            <b>{dayOfMonth(day)}</b>
            <i />
          </button>
        )
      })}
    </div>
  )
}
