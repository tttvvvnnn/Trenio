import type { Attendance, Booking, BookingStatus, Package, PackageStatus } from './api'

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

// День YYYY-MM-DD и время HH:MM в часовом поясе тренера -> момент в ISO (UTC)
export function zonedIso(day: string, time: string, timeZone: string): string {
  const wall = Date.parse(`${day}T${time}:00Z`)
  // Смещение пояса узнаём, отформатировав момент в нём; второй проход — на случай перехода
  // на летнее время между догадкой и ответом
  let guess = wall
  for (let pass = 0; pass < 2; pass++) {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone,
      hourCycle: 'h23',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).formatToParts(new Date(guess))
    const get = (type: string) => parts.find((part) => part.type === type)?.value ?? '00'
    const shown = Date.parse(
      `${get('year')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}:00Z`,
    )
    guess += wall - shown
  }
  return new Date(guess).toISOString()
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

// «Клиент перенёс с пн, 7 января, 10:00» — с точки зрения того, кто смотрит
export function rescheduleNote(booking: Booking, viewer: 'client' | 'trainer'): string | null {
  if (!booking.rescheduled_from || !booking.rescheduled_by) return null
  const from = dateTime(booking.rescheduled_from, booking.trainer.timezone)
  const who =
    booking.rescheduled_by === viewer
      ? 'Вы перенесли'
      : booking.rescheduled_by === 'client'
        ? 'Клиент перенёс'
        : 'Тренер перенёс'
  return `${who} с ${from}`
}

// "Анна Петрова"
export function fullName(person: { first_name: string; last_name: string | null }): string {
  return [person.first_name, person.last_name].filter(Boolean).join(' ')
}

export const ATTENDANCE: Record<Attendance, string> = {
  attended: 'Прошла',
  missed_charged: 'Пропуск, списать',
  missed_free: 'Пропуск, не списывать',
}

// Коротко для списков
export const ATTENDANCE_SHORT: Record<Attendance, string> = {
  attended: 'прошла',
  missed_charged: 'пропуск, списано',
  missed_free: 'пропуск',
}

export const PACKAGE_STATUS: Record<PackageStatus, string> = {
  active: 'Действует',
  finished: 'Закончился',
  expired: 'Истёк срок',
  closed: 'Закрыт',
}

// "2030-01-07" -> "07.01"
export function shortDate(day: string): string {
  return `${day.slice(8, 10)}.${day.slice(5, 7)}`
}

// "2030-01-07" -> "7 января 2030"
export function longDate(day: string): string {
  return new Intl.DateTimeFormat('ru-RU', {
    timeZone: 'UTC',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
    .format(utcNoon(day))
    .replace(/\s*г\.$/, '')
}

// "осталось 2 занятия"
export function sessionsLeft(left: number): string {
  return `осталось ${plural(left, 'занятие', 'занятия', 'занятий')}`
}

// "Персональная · прошла · занятие 3 из 10" — запись в истории клиента и в списках тренера
export function bookingNote(booking: Booking, now = new Date()): string {
  return [booking.service.name, ...bookingState(booking, now)].join(' · ')
}

// "прошла", "занятие 3 из 10" — то же без названия услуги, для строк с листком календаря
export function bookingState(booking: Booking, now = new Date()): string[] {
  const parts: string[] = []
  if (booking.attendance) parts.push(ATTENDANCE_SHORT[booking.attendance])
  else if (booking.status === 'cancelled') parts.push('отменена')
  else if (booking.status === 'declined') parts.push('отклонена')
  else if (new Date(booking.starts_at) <= now) parts.push('не отмечена')
  else if (booking.rescheduled_from) parts.push('перенесена')
  const charge = booking.charge ?? booking.planned
  if (charge) {
    parts.push(`занятие ${charge.number} из ${charge.sessions_count}`)
  } else if (booking.one_off && booking.attendance) {
    parts.push('разовая')
  }
  return parts
}

// "пройдено 3 из 10 · внесено 10 000 ₽ из 20 000 ₽"
export function packageLine(pkg: Package): string {
  const money = pkg.due > 0 ? `внесено ${rubles(pkg.paid)} из ${rubles(pkg.price)}` : 'оплачен'
  return `пройдено ${pkg.used} из ${pkg.sessions_count} · ${money}`
}
