/*
 * Кнопки в уведомлениях бота открывают Trenio сразу на нужном:
 * ?role=trainer&booking=12, ?role=trainer&client=5, ?role=client&tab=book.
 * Ссылку читаем один раз при запуске и отдаём экрану той роли, для которой она.
 */

export type LinkRole = 'trainer' | 'client'

export type LinkTarget = {
  role: LinkRole
  booking?: number
  client?: number
  tab?: string
}

function parse(search: string): LinkTarget | null {
  const params = new URLSearchParams(search)
  const role = params.get('role')
  if (role !== 'trainer' && role !== 'client') return null
  const id = (key: string) => {
    const value = Number(params.get(key))
    return Number.isInteger(value) && value > 0 ? value : undefined
  }
  return { role, booking: id('booking'), client: id('client'), tab: params.get('tab') ?? undefined }
}

let link = typeof window === 'undefined' ? null : parse(window.location.search)

// Для кого ссылка: тренеру, который сам ходит к тренеру, не нужно выбирать профиль
export function linkRole(): LinkRole | null {
  return link?.role ?? null
}

// Забрать ссылку: второй раз она не сработает, например после смены профиля
export function takeLink(role: LinkRole): LinkTarget | null {
  if (link?.role !== role) return null
  const taken = link
  link = null
  return taken
}
