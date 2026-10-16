import { realtimeToken, realtimeUrl } from './api'
import { emitRefresh, invalidate } from './sync'
import { undoPending } from './undo'

/*
 * Живые обновления по WebSocket.
 *
 * Сервер не шлёт данные, только сигнал «у вашего тренера что-то поменялось».
 * На него делаем то же, что при возврате в приложение: помечаем кэш устаревшим
 * и просим экраны перечитать данные. Поэтому экраны о WebSocket ничего не знают.
 *
 * Соединение одно на приложение. В фоне Telegram его всё равно рвёт, поэтому
 * при сворачивании закрываем сами, а при возврате открываем заново. Если связь
 * пропала, пробуем снова с растущей паузой. Без соединения приложение работает
 * как раньше: обновляется при возврате и жестом «потянуть вниз».
 */

const MIN_RETRY_MS = 1000
const MAX_RETRY_MS = 30_000
// Несколько сигналов подряд (например, своё изменение и чужое) — одно обновление
const DEBOUNCE_MS = 300
// Сервер не принял токен: без нового входа переподключаться незачем
const UNAUTHORIZED = 4401

let socket: WebSocket | null = null
let active = false
let connectedOnce = false
let retryMs = MIN_RETRY_MS
let retryTimer: number | undefined
let applyTimer: number | undefined

function scheduleRefresh() {
  window.clearTimeout(applyTimer)
  applyTimer = window.setTimeout(() => {
    // Пока висит «Отменить», свежие данные вернули бы на экран удалённое: подождём
    if (undoPending()) {
      scheduleRefresh()
      return
    }
    invalidate()
    emitRefresh()
  }, DEBOUNCE_MS)
}

function open() {
  const token = realtimeToken()
  if (!active || socket || !token) return
  const ws = new WebSocket(realtimeUrl())
  socket = ws
  ws.onopen = () => ws.send(JSON.stringify({ token }))
  ws.onmessage = (event: MessageEvent) => {
    let type: unknown
    try {
      type = (JSON.parse(String(event.data)) as { type?: unknown }).type
    } catch {
      return
    }
    if (type === 'ready') {
      retryMs = MIN_RETRY_MS
      // Пока соединения не было, сигналы могли пройти мимо
      if (connectedOnce) scheduleRefresh()
      connectedOnce = true
    } else if (type === 'changed') {
      scheduleRefresh()
    }
  }
  ws.onclose = (event: CloseEvent) => {
    // Закрыли сами (свернули приложение или выключили): переподключаться не надо
    if (socket !== ws) return
    socket = null
    if (!active || event.code === UNAUTHORIZED) return
    window.clearTimeout(retryTimer)
    retryTimer = window.setTimeout(open, retryMs)
    retryMs = Math.min(retryMs * 2, MAX_RETRY_MS)
  }
}

function close() {
  window.clearTimeout(retryTimer)
  const ws = socket
  socket = null
  ws?.close(1000)
}

function onVisibility() {
  if (document.visibilityState === 'hidden') {
    close()
  } else {
    retryMs = MIN_RETRY_MS
    open()
  }
}

// Включить живые обновления после входа. Возвращает выключатель
export function startRealtime(): () => void {
  if (typeof WebSocket === 'undefined') return () => {}
  active = true
  open()
  document.addEventListener('visibilitychange', onVisibility)
  return () => {
    active = false
    document.removeEventListener('visibilitychange', onVisibility)
    window.clearTimeout(applyTimer)
    close()
  }
}
