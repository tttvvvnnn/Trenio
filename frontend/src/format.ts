// 0 — понедельник, как в API
export const WEEKDAYS = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
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
