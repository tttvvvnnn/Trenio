import type { FeedKind, TrainerState } from '../api'

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
