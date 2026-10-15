import { reportClientError } from './api'

// Одна и та же ошибка уходит один раз за запуск: сервер ещё и склеивает повторы
const reported = new Set<string>()

export function reportError(error: unknown, screen?: string) {
  const message = error instanceof Error ? `${error.name}: ${error.message}` : String(error)
  if (reported.has(message)) return
  reported.add(message)
  reportClientError({
    message: message.slice(0, 500),
    stack: error instanceof Error ? error.stack?.slice(0, 2000) : undefined,
    screen,
  }).catch(() => {})
}

// Ошибки вне отрисовки: в обработчиках и забытых промисах. Ошибки запросов к API
// экраны показывают сами, их не шлём
export function installErrorReporting() {
  window.addEventListener('error', (event) => {
    reportError(event.error ?? event.message, 'window')
  })
  window.addEventListener('unhandledrejection', (event) => {
    const reason: unknown = event.reason
    if (reason instanceof Error && reason.name === 'ApiError') return
    reportError(reason, 'promise')
  })
}
