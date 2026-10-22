import { SECTIONS, type Section } from './sections'

// Адрес экрана в hash: #/раздел[/номер][?параметры], например #/trainers/12 или #/clients?trainer=12
export type Route = { section: Section; id: number | null; params: URLSearchParams }

export function parseRoute(hash = window.location.hash): Route {
  const [path, query = ''] = hash.replace(/^#\/?/, '').split('?')
  const [name, rawId] = path.split('/')
  const known = SECTIONS.find((item) => item.id === name)
  return {
    section: known ? known.id : 'summary',
    id: known && rawId && /^\d+$/.test(rawId) ? Number(rawId) : null,
    params: new URLSearchParams(query),
  }
}

export function href(section: Section, id?: number | null, params?: Record<string, string | number | null | undefined>): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== null && value !== undefined && value !== '') query.set(key, String(value))
  }
  const suffix = query.toString()
  return `#/${section}${id ? `/${id}` : ''}${suffix ? `?${suffix}` : ''}`
}

export const trainerHref = (id: number) => href('trainers', id)
export const clientHref = (id: number) => href('clients', id)

export function go(target: string) {
  window.location.hash = target.slice(1)
}
