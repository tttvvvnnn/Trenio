import type { ReminderPrefs, ReminderRole, Subscription, Trainer } from './api'
import { localDate, longDate, plural } from './format'

// Варианты настроек и их запись одной строкой для Профиля

// С каким шагом клиенту предлагается время начала; 0 — по длительности услуги
export const SLOT_STEPS: [number, string][] = [
  [5, 'каждые 5 мин'],
  [10, 'каждые 10 мин'],
  [15, 'каждые 15 мин'],
  [20, 'каждые 20 мин'],
  [30, 'каждые 30 мин'],
  [60, 'каждый час'],
  [0, 'по длительности услуги'],
]

// За сколько минут до начала можно напомнить
export const REMINDER_OFFSETS = [
  [15, 'за 15 мин'],
  [30, 'за 30 мин'],
  [60, 'за 1 ч'],
  [120, 'за 2 ч'],
  [180, 'за 3 ч'],
  [1440, 'за сутки'],
  [2880, 'за 2 дня'],
] as const satisfies readonly (readonly [number, string])[]

/** Настройки одной строкой для Профиля: «подтверждаю сам · отмена за 12 ч · каждые 15 мин». */
export function bookingSettingsLine(trainer: Trainer): string {
  const step = SLOT_STEPS.find(([value]) => value === trainer.slot_step_min)?.[1]
  return [
    trainer.auto_confirm ? 'подтверждаются сразу' : 'подтверждаю сам',
    trainer.cancel_hours === 0 ? 'отмена до начала' : `отмена за ${trainer.cancel_hours} ч`,
    step,
  ]
    .filter(Boolean)
    .join(' · ')
}

/** Настройки одной строкой для Профиля: «за 1 ч, за сутки · спрашивать про посещение». */
export function reminderLine(prefs: ReminderPrefs, role: ReminderRole): string {
  const offsets = REMINDER_OFFSETS.filter(([value]) => prefs.offsets.includes(value)).map(
    ([, label]) => label,
  )
  const parts = [prefs.enabled && offsets.length > 0 ? offsets.join(', ') : 'напоминания выкл.']
  if (role === 'trainer' && prefs.attendance_prompt) parts.push('спрашивать про посещение')
  return parts.join(' · ')
}

// «до 18 ноября 2026»
export function untilText(until: string | null, timezone: string): string {
  return until ? `до ${longDate(localDate(until, timezone))}` : ''
}

/** Строка в Профиле: какой тариф и до какого числа. */
export function subscriptionLine(
  sub: Subscription,
  timezone: string,
): { title: string; subtitle: string } {
  switch (sub.state) {
    case 'pro':
      return { title: 'Pro', subtitle: untilText(sub.until, timezone) }
    case 'trial':
      return {
        title: 'Пробный период',
        subtitle: `Всё без ограничений ${untilText(sub.until, timezone)}`,
      }
    case 'free':
      return {
        title: 'Бесплатный тариф',
        subtitle: `${sub.clients} из ${plural(sub.client_limit ?? 0, 'клиента', 'клиентов', 'клиентов')}`,
      }
    default:
      return { title: 'Pro', subtitle: 'Без ограничений' }
  }
}
