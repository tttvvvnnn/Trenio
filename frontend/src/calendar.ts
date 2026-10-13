// Календарь записей тренера: цвета записей и сетка месяца
import type { Booking } from './api'
import { addDays } from './format'

export type Tone = 'planned' | 'pending' | 'alert' | 'done' | 'missed' | 'unmarked'

// Цвет записи: «без блока» важнее статуса, потом отметки и подтверждение
export function bookingTone(booking: Booking, now: Date): Tone {
  if (booking.attendance === 'missed_free' || booking.attendance === 'missed_charged') {
    return booking.out_of_block && booking.attendance === 'missed_charged' ? 'alert' : 'missed'
  }
  if (booking.out_of_block) return 'alert'
  if (booking.attendance === 'attended') return 'done'
  if (booking.status === 'pending') return 'pending'
  if (new Date(booking.starts_at) <= now) return 'unmarked'
  return 'planned'
}

export const TONE_LABEL: Record<Tone, string> = {
  planned: 'запланирована',
  pending: 'ждёт ответа',
  alert: 'без блока',
  done: 'прошла',
  missed: 'пропуск',
  unmarked: 'не отмечена',
}

// Понедельник недели, в которую попадает день
export function weekStart(day: string): string {
  const weekday = (new Date(`${day}T12:00:00Z`).getUTCDay() + 6) % 7
  return addDays(day, -weekday)
}

// Клетки месяца: с понедельника первой недели до воскресенья последней
export function monthDays(month: string): string[] {
  const first = weekStart(month)
  const next = shiftMonth(month, 1)
  const days: string[] = []
  for (let day = first; day < next || days.length % 7 !== 0; day = addDays(day, 1)) {
    days.push(day)
  }
  return days
}

// "2026-10-01", 1 -> "2026-11-01"
export function shiftMonth(month: string, by: number): string {
  const date = new Date(`${month.slice(0, 7)}-01T12:00:00Z`)
  date.setUTCMonth(date.getUTCMonth() + by)
  return date.toISOString().slice(0, 10)
}

// "10:00:00", "14:30:00" -> "10–14:30": в клетке календаря места мало
export function shortRange(start: string, end: string): string {
  const short = (value: string) =>
    value.slice(3, 5) === '00'
      ? String(Number(value.slice(0, 2)))
      : value.slice(0, 5).replace(/^0/, '')
  return `${short(start)}–${short(end)}`
}
