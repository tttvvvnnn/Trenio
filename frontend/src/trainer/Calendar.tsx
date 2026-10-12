import { useEffect, useState } from 'react'

import { fetchServices, fetchSlots, type Service, type Slot } from '../api'
import { dayTitle, localDate, localTime } from '../format'

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

  useEffect(() => {
    Promise.all([fetchSlots(DAYS), fetchServices()])
      .then(([loadedSlots, loadedServices]) => {
        setSlots(loadedSlots)
        setServices(loadedServices)
      })
      .catch((err: unknown) => setError(String(err)))
  }, [])

  if (slots === null) {
    return <p className="hint">{error ?? 'Загрузка…'}</p>
  }

  if (slots.length === 0) {
    return (
      <section>
        <p className="hint">
          На ближайшие две недели свободных окошек нет. Добавьте услуги и рабочие часы, и они появятся
          здесь.
        </p>
        <button type="button" onClick={onGoToSetup}>
          Настроить неделю
        </button>
      </section>
    )
  }

  const names = new Map(services.map((service) => [service.id, service.name]))
  const showService = services.length > 1
  const byDay = new Map<string, Slot[]>()
  for (const slot of slots) {
    const day = localDate(slot.starts_at, timezone)
    byDay.set(day, [...(byDay.get(day) ?? []), slot])
  }

  return (
    <section>
      <p className="hint">Свободные окошки на {DAYS} дней. Так их увидят клиенты.</p>
      {[...byDay.entries()].map(([day, daySlots]) => (
        <div key={day} className="card">
          <div className="card-title">{dayTitle(day)}</div>
          <div className="chips">
            {daySlots.map((slot) => (
              <span key={`${slot.service_id}-${slot.starts_at}`} className="chip">
                {localTime(slot.starts_at, timezone)}
                {showService && <span className="hint"> {names.get(slot.service_id)}</span>}
              </span>
            ))}
          </div>
        </div>
      ))}
    </section>
  )
}
