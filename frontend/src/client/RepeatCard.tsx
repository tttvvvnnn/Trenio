import { useEffect, useState } from 'react'

import {
  createMyBooking,
  errorText,
  fetchMyBookings,
  fetchMyHistory,
  fetchTrainerSlots,
  type Booking,
  type ClientTrainer,
  type Slot,
} from '../api'
import { dateTime, localDate, localTime, weekdayShort } from '../format'
import { useRefreshKey } from '../sync'
import { haptic } from '../telegram'
import { DateLeaf } from '../ui/BookingDays'
import { ErrorText } from '../ui/kit'

// На сколько дней вперёд ищем такое же окошко
const SEARCH_DAYS = 14

type Props = {
  trainer: ClientTrainer
  onBooked: (booking: Booking) => void
}

/**
 * «Как в прошлый раз»: та же услуга, тот же день недели и время, что в последней записи.
 * Ищем ближайшее свободное такое окошко в следующие две недели; нет его — нет и карточки.
 */
export default function RepeatCard({ trainer, onBooked }: Props) {
  const [found, setFound] = useState<{ last: Booking; slot: Slot } | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const refreshKey = useRefreshKey()
  const timezone = trainer.timezone

  useEffect(() => {
    let stale = false
    async function find() {
      const [upcoming, history] = await Promise.all([fetchMyBookings(), fetchMyHistory()])
      const own = (items: Booking[]) =>
        items.filter(
          (item) =>
            item.trainer.id === trainer.id &&
            item.status !== 'cancelled' &&
            item.status !== 'declined',
        )
      // Последняя — самая поздняя по времени: будущая, если есть, иначе прошедшая
      const last = [...own(upcoming), ...own(history)].sort(
        (a, b) => Date.parse(b.starts_at) - Date.parse(a.starts_at),
      )[0]
      if (!last) return null
      const today = localDate(new Date(), timezone)
      const slots = await fetchTrainerSlots(trainer.id, last.service.id, SEARCH_DAYS, today)
      const weekday = weekdayShort(localDate(last.starts_at, timezone))
      const time = localTime(last.starts_at, timezone)
      const slot = slots.find(
        (item) =>
          weekdayShort(localDate(item.starts_at, timezone)) === weekday &&
          localTime(item.starts_at, timezone) === time,
      )
      return slot ? { last, slot } : null
    }
    // Карточка необязательная: не нашли или не загрузилось — просто не показываем
    find()
      .then((result) => {
        if (!stale) setFound(result)
      })
      .catch(() => {
        if (!stale) setFound(null)
      })
    return () => {
      stale = true
    }
  }, [trainer.id, timezone, refreshKey])

  if (!found) return null
  const { last, slot } = found

  async function book() {
    if (saving) return
    setSaving(true)
    setError(null)
    try {
      const booking = await createMyBooking({
        trainer_id: trainer.id,
        service_id: slot.service_id,
        starts_at: slot.starts_at,
      })
      haptic.success()
      setFound(null)
      onBooked(booking)
    } catch (err) {
      haptic.error()
      setError(errorText(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="section">
      <div className="group repeat-card">
        <DateLeaf day={localDate(slot.starts_at, timezone)} />
        <span className="row-text">
          <span className="row-title">Как в прошлый раз</span>
          <span className="row-subtitle">
            {last.service.name} · {dateTime(slot.starts_at, timezone)}
          </span>
        </span>
        <button type="button" className="pill-button" disabled={saving} onClick={() => void book()}>
          {saving ? 'Записываем…' : 'Записаться'}
        </button>
      </div>
      {error && <ErrorText>{error}</ErrorText>}
    </section>
  )
}
