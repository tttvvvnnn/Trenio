// В проде Mini App и API живут на одном домене, поэтому по умолчанию адрес пустой
const API_URL = import.meta.env.VITE_API_URL ?? ''

export type Trainer = {
  id: number
  display_name: string
  timezone: string
  address: string | null
  auto_confirm: boolean
  cancel_hours: number
  // null: тренер ещё не прошёл первую настройку
  onboarded_at: string | null
}

export type Me = {
  id: number
  first_name: string
  last_name: string | null
  username: string | null
  is_trainer: boolean
  is_admin: boolean
  trainer: Trainer | null
}

export type TrainerProfileInput = Partial<
  Pick<Trainer, 'display_name' | 'timezone' | 'address' | 'auto_confirm' | 'cancel_hours'>
>

export type Service = {
  id: number
  name: string
  duration_min: number
  capacity: number
  price: number | null
  address: string | null
  is_active: boolean
}

export type ServiceInput = {
  name: string
  duration_min: number
  capacity: number
  price: number | null
  address: string | null
}

// Время приходит как "10:00:00"
export type Rule = {
  id: number
  weekday: number
  start: string
  end: string
  service_ids: number[]
}

export type RuleInput = Omit<Rule, 'id'>

export type ExceptionKind = 'closed' | 'extra'

export type ScheduleException = {
  id: number
  day: string
  kind: ExceptionKind
  start: string | null
  end: string | null
}

export type ExceptionInput = Omit<ScheduleException, 'id'>

export type Slot = {
  service_id: number
  starts_at: string
  ends_at: string
}

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

let accessToken: string | null = null

// FastAPI кладёт текст ошибки в detail: строкой или списком ошибок валидации
function errorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const { detail } = body as { detail: unknown }
    if (typeof detail === 'string') {
      return detail
    }
    if (Array.isArray(detail)) {
      return 'Проверьте заполнение полей'
    }
  }
  return fallback
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`)
  }
  const response = await fetch(`${API_URL}${path}`, { ...init, headers })
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null)
    throw new ApiError(response.status, errorMessage(body, `${response.status} ${response.statusText}`))
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  return request<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) })
}

export async function loginWithTelegram(initData: string): Promise<void> {
  const { access_token } = await send<{ access_token: string }>('POST', '/api/auth/telegram', {
    init_data: initData,
  })
  accessToken = access_token
}

export function fetchMe(): Promise<Me> {
  return request<Me>('/api/me')
}

export function updateTrainer(changes: TrainerProfileInput): Promise<Trainer> {
  return send<Trainer>('PATCH', '/api/trainer/me', changes)
}

export function fetchServices(includeInactive = false): Promise<Service[]> {
  return request<Service[]>(`/api/trainer/services?include_inactive=${includeInactive}`)
}

export function createService(service: ServiceInput): Promise<Service> {
  return send<Service>('POST', '/api/trainer/services', service)
}

export function updateService(
  id: number,
  changes: Partial<ServiceInput> & { is_active?: boolean },
): Promise<Service> {
  return send<Service>('PATCH', `/api/trainer/services/${id}`, changes)
}

export function fetchRules(): Promise<Rule[]> {
  return request<Rule[]>('/api/trainer/schedule/rules')
}

export function createRule(rule: RuleInput): Promise<Rule> {
  return send<Rule>('POST', '/api/trainer/schedule/rules', rule)
}

export function replaceRule(id: number, rule: RuleInput): Promise<Rule> {
  return send<Rule>('PUT', `/api/trainer/schedule/rules/${id}`, rule)
}

export function deleteRule(id: number): Promise<void> {
  return send<void>('DELETE', `/api/trainer/schedule/rules/${id}`)
}

export function fetchExceptions(from: string, to: string): Promise<ScheduleException[]> {
  return request<ScheduleException[]>(`/api/trainer/schedule/exceptions?from=${from}&to=${to}`)
}

export function createException(exception: ExceptionInput): Promise<ScheduleException> {
  return send<ScheduleException>('POST', '/api/trainer/schedule/exceptions', exception)
}

export function deleteException(id: number): Promise<void> {
  return send<void>('DELETE', `/api/trainer/schedule/exceptions/${id}`)
}

export function fetchSlots(days = 14): Promise<Slot[]> {
  return request<Slot[]>(`/api/trainer/slots?days=${days}`)
}
