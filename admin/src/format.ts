const TZ = 'Europe/Moscow'

export const rub = (value: number) => `${value.toLocaleString('ru-RU')} ₽`

export const shortDate = (iso: string) =>
  new Date(iso).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', timeZone: TZ })

export const time = (iso: string) =>
  new Date(iso).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', timeZone: TZ })

export const monthName = (iso: string) =>
  new Date(iso).toLocaleDateString('ru-RU', { month: 'short', timeZone: 'UTC' }).replace('.', '')

export const today = () =>
  new Date().toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long', timeZone: TZ })

// «сегодня 17:52», «вчера», «6 дней назад»
export function ago(iso: string | null): string {
  if (!iso) return 'не заходил'
  const then = new Date(iso)
  const dayKey = (d: Date) => d.toLocaleDateString('ru-RU', { timeZone: TZ })
  const now = new Date()
  if (dayKey(then) === dayKey(now)) return `сегодня ${time(iso)}`
  const days = Math.max(1, Math.round((now.getTime() - then.getTime()) / 86_400_000))
  if (days === 1) return 'вчера'
  return `${days} ${plural(days, 'день', 'дня', 'дней')} назад`
}

export function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few
  return many
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('')
}

const AVATAR_COLORS = ['#6366F1', '#EC4899', '#0EA5E9', '#14B8A6', '#F59E0B', '#8B5CF6', '#EF4444']

export const avatarColor = (id: number) => AVATAR_COLORS[id % AVATAR_COLORS.length]

// Фон-подложка под цвет: прозрачная версия того же цвета
export const tint = (cssVar: string) =>
  `color-mix(in srgb, ${cssVar} var(--tint-alpha), transparent)`
