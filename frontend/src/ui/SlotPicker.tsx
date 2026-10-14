import { useEffect, useState } from 'react'

import type { Slot } from '../api'
import { monthDays } from '../calendar'
import { dayTitle, localDate, localTime, plural, zonedIso } from '../format'
import { haptic } from '../telegram'
import { ErrorText, InlineField } from './kit'
import MonthGrid from './MonthGrid'

type Props = {
  timezone: string
  // Вместимость услуги: у групповых показываем свободные места
  capacity: number
  // Окошки на count дней с from; перезагружаются при смене месяца и reloadKey
  load: (from: string, count: number) => Promise<Slot[]>
  // Меняется, когда окошки нужно перечитать: например, выбрали другую услугу
  reloadKey: string
  // Выбранное начало, ISO; null — ничего не выбрано
  value: string | null
  onChange: (startsAt: string | null) => void
  // Тренер может поставить любое время, не только из окошек
  allowCustom?: boolean
  // С какого дня открыть
  initialDay?: string
}

/** Выбор времени: месяц со свободными днями, окошки дня, для тренера — своё время. */
export default function SlotPicker({
  timezone,
  capacity,
  load,
  reloadKey,
  value,
  onChange,
  allowCustom = false,
  initialDay,
}: Props) {
  const today = localDate(new Date(), timezone)
  const start = initialDay && initialDay >= today ? initialDay : today
  const [month, setMonth] = useState(`${start.slice(0, 7)}-01`)
  const [day, setDay] = useState(start)
  const [slots, setSlots] = useState<{ key: string; items: Slot[] } | null>(null)
  const [custom, setCustom] = useState('')
  const [error, setError] = useState<string | null>(null)
  const key = `${reloadKey}:${month}`

  useEffect(() => {
    let stale = false
    const days = monthDays(month)
    const last = days[days.length - 1]
    // В прошлое не записывают и не переносят
    const first = days[0] > today ? days[0] : today
    if (first > last) {
      setSlots({ key, items: [] })
      return
    }
    const count = Math.round((Date.parse(last) - Date.parse(first)) / 86_400_000) + 1
    load(first, count)
      .then((loaded) => {
        if (!stale) setSlots({ key, items: loaded })
      })
      .catch((err: unknown) => setError(String(err)))
    return () => {
      stale = true
    }
    // load меняется на каждом рендере родителя; перечитываем по key
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, today])

  const byDay = new Map<string, Slot[]>()
  for (const slot of slots?.key === key ? slots.items : []) {
    const slotDay = localDate(slot.starts_at, timezone)
    byDay.set(slotDay, [...(byDay.get(slotDay) ?? []), slot])
  }
  const daySlots = byDay.get(day) ?? []
  const loading = slots?.key !== key

  function pickDay(next: string) {
    setDay(next)
    setCustom('')
    onChange(null)
  }

  return (
    <>
      <MonthGrid
        month={month}
        today={today}
        isSelected={(item) => item === day}
        loading={loading}
        compact
        onMonth={(next) => {
          setMonth(next)
          pickDay(next.slice(0, 7) === today.slice(0, 7) ? today : next)
        }}
        onSelect={pickDay}
        dayClass={(item) =>
          byDay.has(item) ? 'free' : allowCustom && item >= today ? undefined : 'empty'
        }
        dayLabel={(item) =>
          `${dayTitle(item)}: ${byDay.has(item) ? 'есть свободное время' : 'нет свободного времени'}`
        }
        renderDay={(item) => (byDay.has(item) ? <i className="month-free" /> : null)}
      />
      <h2 className="section-title day-title">{dayTitle(day)}</h2>
      {!loading && daySlots.length === 0 && (
        <p className="section-footer">
          {day < today
            ? 'Этот день уже прошёл.'
            : allowCustom
              ? 'Свободных окошек нет, но можно указать своё время.'
              : 'В этот день свободного времени нет.'}
        </p>
      )}
      {daySlots.length > 0 && (
        <section className="section">
          <div className="group">
            <div className="times" role="radiogroup" aria-label="Время">
              {daySlots.map((slot) => (
                <button
                  key={slot.starts_at}
                  type="button"
                  role="radio"
                  className="time"
                  aria-checked={value === slot.starts_at && custom === ''}
                  onClick={() => {
                    haptic.select()
                    setCustom('')
                    onChange(slot.starts_at)
                  }}
                >
                  {localTime(slot.starts_at, timezone)}
                  {capacity > 1 && (
                    <small>{plural(slot.seats_left, 'место', 'места', 'мест')}</small>
                  )}
                </button>
              ))}
            </div>
          </div>
        </section>
      )}
      {allowCustom && day >= today && (
        <section className="section">
          <div className="group">
            <InlineField label="Другое время">
              {(id) => (
                <input
                  id={id}
                  className="row-input"
                  type="time"
                  step={300}
                  value={custom}
                  onChange={(event) => {
                    const time = event.target.value
                    setCustom(time)
                    onChange(time ? zonedIso(day, time, timezone) : null)
                  }}
                />
              )}
            </InlineField>
          </div>
          <p className="section-footer">
            Вне окошек расписания: проверим только, что у вас нет другого занятия.
          </p>
        </section>
      )}
      {error && <ErrorText>{error}</ErrorText>}
    </>
  )
}
