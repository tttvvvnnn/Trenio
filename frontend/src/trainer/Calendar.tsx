import { useEffect, useState } from 'react'

import { fetchServices, fetchSlots, type Service, type Slot } from '../api'
import {
  addDays,
  dayOfMonth,
  dayTitle,
  duration,
  localDate,
  localTime,
  plural,
  weekdayShort,
} from '../format'
import { haptic } from '../telegram'
import { EmptyState, ErrorText, PageHeader, SkeletonList } from '../ui/kit'

// Сколько дней вперёд показываем окошки
const DAYS = 14

type Props = {
  timezone: string
  onGoToSetup: () => void
}

export default function Calendar({ timezone, onGoToSetup }: Props) {
  const [slots, setSlots] = useState<Slot[] | null>(null)
  const [services, setServices] = useState<Service[]>([])
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([fetchSlots(DAYS), fetchServices()])
      .then(([loadedSlots, loadedServices]) => {
        setSlots(loadedSlots)
        setServices(loadedServices)
      })
      .catch((err: unknown) => setError(String(err)))
  }, [])

  const header = (
    <PageHeader title="Окошки" subtitle="Свободное время на 2 недели. Так его видят клиенты." />
  )

  if (slots === null) {
    return (
      <>
        {header}
        {error ? <ErrorText>{error}</ErrorText> : <SkeletonList rows={2} />}
      </>
    )
  }

  if (slots.length === 0) {
    return (
      <>
        <PageHeader title="Окошки" />
        <EmptyState
          icon="calendar"
          title="Пока нет свободного времени"
          text="Добавьте услугу и рабочие часы, и окошки появятся здесь."
          action={{ label: 'Настроить расписание', onClick: onGoToSetup }}
        />
      </>
    )
  }

  const byDay = new Map<string, Slot[]>()
  for (const slot of slots) {
    const day = localDate(slot.starts_at, timezone)
    byDay.set(day, [...(byDay.get(day) ?? []), slot])
  }
  const today = localDate(new Date(), timezone)
  const days = Array.from({ length: DAYS }, (_, index) => addDays(today, index))
  // По умолчанию открыт ближайший день со свободным временем
  const current = selected ?? days.find((day) => byDay.has(day)) ?? today
  const daySlots = byDay.get(current) ?? []

  return (
    <>
      {header}
      <div className="date-strip" role="group" aria-label="Дни">
        {days.map((day) => {
          const count = byDay.get(day)?.length ?? 0
          return (
            <button
              key={day}
              type="button"
              className={count === 0 ? 'date empty' : 'date'}
              aria-pressed={day === current}
              aria-label={`${dayTitle(day)}, ${count === 0 ? 'нет окошек' : plural(count, 'окошко', 'окошка', 'окошек')}`}
              onClick={() => {
                haptic.select()
                setSelected(day)
              }}
            >
              <small>{weekdayShort(day)}</small>
              <b>{dayOfMonth(day)}</b>
              <i />
            </button>
          )
        })}
      </div>
      <h2 className="section-title day-title">{dayTitle(current)}</h2>
      {daySlots.length === 0 ? (
        <p className="section-footer">В этот день свободного времени нет.</p>
      ) : (
        <div className="stack">
          {services
            .filter((service) => daySlots.some((slot) => slot.service_id === service.id))
            .map((service) => (
              <div key={service.id} className="group">
                <div className="service-head">
                  <strong>{service.name}</strong>
                  <span>
                    {duration(service.duration_min)}
                    {service.capacity > 1 && ` · до ${service.capacity} чел.`}
                  </span>
                </div>
                <div className="times">
                  {daySlots
                    .filter((slot) => slot.service_id === service.id)
                    .map((slot) => (
                      <span key={slot.starts_at} className="time">
                        {localTime(slot.starts_at, timezone)}
                      </span>
                    ))}
                </div>
              </div>
            ))}
        </div>
      )}
    </>
  )
}
