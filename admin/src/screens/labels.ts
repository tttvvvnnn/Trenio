import type { AdminTrainer, AuditEntry, PromoCode, FeedKind, TicketKind, TrainerState } from '../api'
import { plural, rub, shortDate } from '../format'

export const STATE_LABEL: Record<TrainerState, string> = {
  active: 'работает',
  quiet: 'затих',
  not_set_up: 'не настроен',
  disabled: 'отключён',
}

export const STATE_COLOR: Record<TrainerState, string> = {
  active: 'var(--green)',
  quiet: 'var(--red)',
  not_set_up: 'var(--amber)',
  disabled: 'var(--muted)',
}

export const FEED_LABEL: Record<FeedKind, string> = {
  joined: 'новый тренер',
  first_client: 'первый клиент',
  first_client_booking: 'клиент записался сам',
  first_package: 'первый абонемент',
  quiet: 'затих',
  error: 'сбой',
}

export const FEED_COLOR: Record<FeedKind, string> = {
  joined: 'var(--blue)',
  first_client: 'var(--blue)',
  first_client_booking: 'var(--coral)',
  first_package: 'var(--violet)',
  quiet: 'var(--amber)',
  error: 'var(--red)',
}

export const ATTENTION_TEXT: Record<string, (count: number) => string> = {
  not_set_up: (n) => `не закончил настройку (${n} дн.)`,
  no_clients: (n) => `нет ни одного клиента (${n} дн.)`,
  quiet: (n) => `нет записей ${n} дн.`,
  unmarked: (n) => `${n} занятий без отметки`,
}

const str = (value: unknown) => (typeof value === 'string' || typeof value === 'number' ? String(value) : '')

// Строка журнала простыми словами; неизвестное действие показываем как есть
export function auditText(entry: AuditEntry): string {
  const p = entry.payload
  const name = str(p.name)
  switch (entry.action) {
    case 'login.requested':
      return 'Запрос входа, ждёт подтверждения в боте'
    case 'login.confirmed':
      return 'Вход подтверждён в боте'
    case 'login.denied':
      return 'Вход отклонён в боте'
    case 'login.rejected':
      return 'Попытка входа не админа'
    case 'session.revoked':
      return 'Вход завершён'
    case 'trainer.disabled':
      return `Отключён тренер ${name}`
    case 'trainer.enabled':
      return `Возвращён доступ тренеру ${name}`
    case 'trainer.pro_extended':
      return `${name}: Pro в подарок на ${str(p.days)} дн.`
    case 'trainer.messaged':
      return `Сообщение тренеру ${name}: «${str(p.text).slice(0, 80)}»`
    case 'trainer.deleted':
      return `Удалён тренер ${name}. Причина: ${str(p.reason)}`
    case 'client.deleted':
      return `Удалены данные клиента ${name}. Запрос: ${str(p.reason)}`
    case 'invite.created':
      return 'Создана ссылка-приглашение'
    case 'promo.updated':
      return 'Изменены настройки промо TVPN'
    case 'plans.updated':
      return 'Изменён тариф'
    case 'promo_code.created':
      return `Создан промокод ${str(p.code)}`
    case 'promo_code.enabled':
      return `Включён промокод ${str(p.code)}`
    case 'promo_code.disabled':
      return `Выключен промокод ${str(p.code)}`
    case 'support.answered':
      return `Ответ на обращение ${name}: «${str(p.text).slice(0, 80)}»`
    case 'support.closed':
      return `Закрыто обращение ${name}`
    case 'support.reopened':
      return `Возвращено в работу обращение ${name}`
    case 'broadcast.sent':
      return `Рассылка, получателей ${str(p.recipients)}: «${str(p.text).slice(0, 80)}»`
    default:
      return entry.target ? `${entry.action} · ${entry.target}` : entry.action
  }
}

export function planText(trainer: AdminTrainer): string {
  const now = new Date()
  if (trainer.pro_until && new Date(trainer.pro_until) > now) return `Pro до ${shortDate(trainer.pro_until)}`
  if (trainer.trial_until && new Date(trainer.trial_until) > now) return `пробный до ${shortDate(trainer.trial_until)}`
  return 'бесплатный'
}

export const TICKET_KIND: Record<TicketKind, { label: string; color: string }> = {
  question: { label: 'Вопрос', color: 'var(--blue)' },
  problem: { label: 'Проблема', color: 'var(--red)' },
  idea: { label: 'Идея', color: 'var(--violet)' },
  review: { label: 'Отзыв', color: 'var(--green)' },
}

export function codeValue(code: Pick<PromoCode, 'kind' | 'value'>): string {
  if (code.kind === 'percent') return `−${code.value}% на оплату`
  if (code.kind === 'rubles') return `−${rub(code.value)} на оплату`
  return `${code.value} ${plural(code.value, 'день', 'дня', 'дней')} Pro`
}
