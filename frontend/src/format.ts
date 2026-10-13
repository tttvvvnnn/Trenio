import type { BookingStatus } from './api'

// 0 — понедельник, как в API
export const WEEKDAYS = [
  'Понедельник',
  'Вторник',
  'Среда',
  'Четверг',
  'Пятница',
  'Суббота',
  'Воскресенье',
]
export const WEEKDAYS_SHORT = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

// Часовые пояса России; часовой пояс телефона добавляется, если его нет в списке
const RUSSIAN_TIMEZONES: [string, string][] = [
  ['Europe/Kaliningrad', 'Калининград (МСК−1)'],
  ['Europe/Moscow', 'Москва (МСК)'],
  ['Europe/Samara', 'Самара (МСК+1)'],
  ['Asia/Yekaterinburg', 'Екатеринбург (МСК+2)'],
  ['Asia/Omsk', 'Омск (МСК+3)'],
  ['Asia/Novosibirsk', 'Новосибирск (МСК+4)'],
  ['Asia/Krasnoyarsk', 'Красноярск (МСК+4)'],
  ['Asia/Irkutsk', 'Иркутск (МСК+5)'],
  ['Asia/Yakutsk', 'Якутск (МСК+6)'],
  ['Asia/Vladivostok', 'Владивосток (МСК+7)'],
  ['Asia/Magadan', 'Магадан (МСК+8)'],
  ['Asia/Kamchatka', 'Камчатка (МСК+9)'],
]

export function timezoneOptions(current: string): [string, string][] {
  const options = [...RUSSIAN_TIMEZONES]
  const device = Intl.DateTimeFormat().resolvedOptions().timeZone
  for (const zone of [current, device]) {
    if (zone && zone.includes('/') && !options.some(([value]) => value === zone)) {
      options.push([zone, zone])
    }
  }
  return options
}

export function deviceTimezone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone
}

// "10:00:00" -> "10:00"
export function hhmm(value: string | null): string {
  return value ? value.slice(0, 5) : ''
}

// Дата YYYY-MM-DD в часовом поясе тренера
export function localDate(iso: string | Date, timeZone: string): string {
  // Локаль en-CA форматирует дату как YYYY-MM-DD
  return new Intl.DateTimeFormat('en-CA', { timeZone }).format(new Date(iso))
}

export function localTime(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat('ru-RU', { timeZone, hour: '2-digit', minute: '2-digit' }).format(
    new Date(iso),
  )
}

// "2030-01-07" -> "пн, 7 января"
export function dayTitle(day: string): string {
  const date = new Date(`${day}T12:00:00Z`)
  return new Intl.DateTimeFormat('ru-RU', {
    timeZone: 'UTC',
    weekday: 'short',
    day: 'numeric',
    month: 'long',
  }).format(date)
}

export function addDays(day: string, days: number): string {
  const date = new Date(`${day}T12:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

export function duration(minutes: number): string {
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  if (hours === 0) return `${rest} мин`
  return rest === 0 ? `${hours} ч` : `${hours} ч ${rest} мин`
}

export function rubles(amount: number): string {
  return `${amount.toLocaleString('ru-RU')} ₽`
}

function utcNoon(day: string): Date {
  return new Date(`${day}T12:00:00Z`)
}

// "2030-01-07" -> "пн"
export function weekdayShort(day: string): string {
  return new Intl.DateTimeFormat('ru-RU', { timeZone: 'UTC', weekday: 'short' }).format(
    utcNoon(day),
  )
}

// "2030-01-07" -> 7
export function dayOfMonth(day: string): number {
  return utcNoon(day).getUTCDate()
}

// "2030-01-07" -> "Январь 2030"
export function monthTitle(day: string): string {
  const title = new Intl.DateTimeFormat('ru-RU', {
    timeZone: 'UTC',
    month: 'long',
    year: 'numeric',
  }).format(utcNoon(day))
  return (title.charAt(0).toUpperCase() + title.slice(1)).replace(/\s*г\.$/, '')
}

// "2030-01-07", "2030-01-13" -> "7–13 января"; разные месяцы -> "28 января – 3 февраля"
export function dateRange(first: string, last: string): string {
  const format = (day: string) =>
    new Intl.DateTimeFormat('ru-RU', { timeZone: 'UTC', day: 'numeric', month: 'long' }).format(
      utcNoon(day),
    )
  if (first === last) return dayTitle(first)
  if (first.slice(0, 7) === last.slice(0, 7)) {
    return `${dayOfMonth(first)}–${format(last)}`
  }
  return `${format(first)} – ${format(last)}`
}

// 1 день, 2 дня, 5 дней
export function plural(count: number, one: string, few: string, many: string): string {
  const rule = new Intl.PluralRules('ru-RU').select(count)
  const word = rule === 'one' ? one : rule === 'few' ? few : many
  return `${count} ${word}`
}

// "пн, 7 января, 10:00" в часовом поясе тренера
export function dateTime(iso: string, timeZone: string): string {
  return `${dayTitle(localDate(iso, timeZone))}, ${localTime(iso, timeZone)}`
}

export const BOOKING_STATUS: Record<BookingStatus, string> = {
  pending: 'Ждёт подтверждения',
  confirmed: 'Подтверждена',
  declined: 'Отклонена',
  cancelled: 'Отменена',
}

// "Анна Петрова"
export function fullName(person: { first_name: string; last_name: string | null }): string {
  return [person.first_name, person.last_name].filter(Boolean).join(' ')
}
