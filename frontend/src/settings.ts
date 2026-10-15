import type { ReminderPrefs, ReminderRole, Trainer } from './api'

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
