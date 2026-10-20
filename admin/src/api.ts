// Админка и API живут на одном домене: кука входа уходит сама, а изменяющие запросы
// несут CSRF-токен, полученный после подтверждения входа
const API_URL = import.meta.env.VITE_API_URL ?? ''

let csrfToken: string | null = null

export function setCsrfToken(token: string | null) {
  csrfToken = token
}

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (method !== 'GET' && csrfToken) headers['X-CSRF-Token'] = csrfToken
  const response = await fetch(`${API_URL}/api${path}`, {
    method,
    headers,
    credentials: 'same-origin',
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    let detail = response.statusText
    try {
      const data = (await response.json()) as { detail?: unknown }
      if (typeof data.detail === 'string') detail = data.detail
    } catch {
      // ответ без JSON: оставляем текст статуса
    }
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const get = <T>(path: string) => request<T>('GET', path)
export const post = <T>(path: string, body?: unknown) => request<T>('POST', path, body)
export const put = <T>(path: string, body: unknown) => request<T>('PUT', path, body)

// --- вход ---

export type SessionState = 'pending' | 'active' | 'denied' | 'expired'

export type Session = {
  state: SessionState
  name: string
  expires_at: string
  csrf_token: string | null
}

export type ActiveSession = {
  id: string
  ip: string | null
  user_agent: string | null
  created_at: string
  last_seen_at: string | null
  current: boolean
}

export type TelegramLogin = {
  id: number
  first_name?: string
  last_name?: string
  username?: string
  photo_url?: string
  auth_date: number
  hash: string
}

// --- данные экранов ---

export type Overview = {
  users: number
  users_seen_week: number
  users_active_today: number
  trainers_engaged: number
  trainers: number
  trainers_active: number
  trainers_disabled: number
  clients: number
  clients_new_week: number
  clients_offline: number
  bookings_week: number
  attended_week: number
  upcoming_week: number
  invites_open: number
  notifications_sent_day: number
  notifications_failed_day: number
  version: string
  weeks: { start: string; new_clients: number; new_trainers: number }[]
  funnel: {
    trainers: number
    onboarded: number
    set_up: number
    with_clients: number
    with_bookings: number
  }
}

export type FeedKind =
  | 'joined'
  | 'first_client'
  | 'first_client_booking'
  | 'first_package'
  | 'quiet'
  | 'error'

export type Insights = {
  pulse: { live_trainers: number[]; sessions: number[]; self_booked: (number | null)[] }
  attention: { trainer_id: number; reason: string; count: number }[]
  feed: { at: string; kind: FeedKind; text: string; trainer_id: number | null }[]
  cohort_points: number[]
  cohorts: { start: string; trainers: number; alive: (number | null)[] }[]
  usage: { base: number; features: Record<string, number> }
  health: {
    version: string
    errors_day: number
    notifications_sent_day: number
    notifications_failed_day: number
  }
}

export type TrainerState = 'active' | 'quiet' | 'not_set_up' | 'disabled'

export type AdminTrainer = {
  id: number
  display_name: string
  avatar_url: string | null
  user: { id: number; first_name: string; last_name: string | null; username: string | null }
  state: TrainerState
  is_admin: boolean
  since: string
  timezone: string
  clients: number
  clients_new_week: number
  bookings_month: number
  attended_month: number
  services: number
  last_booking_at: string | null
  last_seen_at: string | null
  active_days: boolean[]
  streak: number
  bookings_created: number
  marks: number
  trial_until: string | null
  pro_until: string | null
}

export type Risk = 'low' | 'medium' | 'high'

export type Money = {
  mrr: number
  paying: number
  trials: number
  arpu: number
  trial_conversion: number | null
  received_total: number
  months: { month: string; received: number }[]
  forecast: { optimistic: number; realistic: number; cautious: number }
  renewals: {
    trainer_id: number
    name: string
    at: string
    kind: 'pro' | 'trial'
    price: number
    risk: Risk
    reason: string
  }[]
  payments: {
    paid_at: string
    trainer_id: number
    name: string
    plan: string
    price: number
    bot: string | null
  }[]
}

export type OpenInvite = { created_at: string; expires_at: string }
export type NewInvite = { url: string; expires_at: string }

export type TrainerRef = { id: number; name: string }

export type AdminClient = {
  id: number
  first_name: string
  last_name: string | null
  username: string | null
  avatar_url: string | null
  offline: boolean
  deleted: boolean
  trainers: TrainerRef[]
  since: string
  bookings: number
  attended: number
  last_booking_at: string | null
  next_booking_at: string | null
  last_seen_at: string | null
  active_days: number
}

export type ClientCard = {
  client: AdminClient
  telegram_id: number | null
  is_trainer: boolean
  links: {
    trainer: TrainerRef
    since: string
    bookings: number
    attended: number
    missed: number
    cancelled: number
    open_packages: number
    last_booking_at: string | null
    next_booking_at: string | null
  }[]
  history: {
    starts_at: string
    trainer: string
    service: string
    status: 'pending' | 'confirmed' | 'declined' | 'cancelled'
    attendance: 'attended' | 'missed_charged' | 'missed_free' | null
    created_by: 'client' | 'trainer'
  }[]
  activity: boolean[]
}

export type Terms = { price_month: number; trial_days: number; free_client_limit: number }

export type PromoSettings = {
  enabled: boolean
  title: string
  subtitle: string
  text: string
  code: string
  url: string
  button: string
  delay_days: number
}

export type AdminPromo = {
  settings: PromoSettings
  stats: { shown: number; dismissed: number; claimed: number; opened: number }
}

export type Segment = 'all' | 'pro' | 'trial' | 'free' | 'not_set_up' | 'quiet'

export type BroadcastItem = {
  id: number
  text: string
  segment: Segment
  with_button: boolean
  recipients: number
  sent: number
  failed: number
  pending: number
  created_at: string
}

export type AuditEntry = {
  id: number
  action: string
  target: string | null
  payload: Record<string, unknown>
  ip: string | null
  web: boolean
  created_at: string
}
