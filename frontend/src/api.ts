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

let accessToken: string | null = null

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`)
  }
  const response = await fetch(`${API_URL}${path}`, { ...init, headers })
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`)
  }
  return (await response.json()) as T
}

export async function loginWithTelegram(initData: string): Promise<void> {
  const { access_token } = await request<{ access_token: string }>('/api/auth/telegram', {
    method: 'POST',
    body: JSON.stringify({ init_data: initData }),
  })
  accessToken = access_token
}

export function fetchMe(): Promise<Me> {
  return request<Me>('/api/me')
}
