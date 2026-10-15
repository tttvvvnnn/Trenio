import { useEffect, useRef, useState } from 'react'

import { emitRefresh, invalidate, pendingCount, subscribePending, useOnline } from '../sync'
import { haptic } from '../telegram'
import { flushUndo } from '../undo'
import BrandMark from './BrandMark'
import Icon from './icons'

// Насколько потянуть вниз, чтобы обновить
const TRIGGER = 64
const MAX_PULL = 96
// Свёрнутое дольше этого приложение при возврате обновляет текущий экран
const STALE_AFTER_MS = 30_000
// Секундомер крутится хотя бы столько, иначе мелькает
const MIN_SPIN_MS = 700
const MAX_SPIN_MS = 8000

function refreshAll() {
  flushUndo()
  invalidate()
  emitRefresh()
}

// Где прокручивается то, что под пальцем: вложенный экран или сама страница
function scrollTop(target: EventTarget | null): number {
  const overlay = target instanceof Element ? target.closest('.screen-overlay') : null
  return overlay ? overlay.scrollTop : window.scrollY
}

/**
 * Обновление данных: жестом «потянуть вниз» с крутящимся секундомером
 * и само, когда приложение снова открыли после сворачивания.
 */
export default function Refresher() {
  const [pull, setPull] = useState(0)
  const [spinning, setSpinning] = useState(false)
  const start = useRef<number | null>(null)
  const pulled = useRef(0)

  useEffect(() => {
    let hiddenAt: number | null = null
    function onVisibility() {
      if (document.visibilityState === 'hidden') {
        hiddenAt = Date.now()
        return
      }
      if (hiddenAt !== null && Date.now() - hiddenAt >= STALE_AFTER_MS) refreshAll()
      hiddenAt = null
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => document.removeEventListener('visibilitychange', onVisibility)
  }, [])

  useEffect(() => {
    if (spinning) return
    function onStart(event: TouchEvent) {
      start.current =
        event.touches.length === 1 && scrollTop(event.target) <= 0 ? event.touches[0].clientY : null
    }
    function onMove(event: TouchEvent) {
      if (start.current === null) return
      const distance = event.touches[0].clientY - start.current
      if (distance <= 0 || scrollTop(event.target) > 0) {
        pulled.current = 0
        setPull(0)
        return
      }
      const next = Math.min(distance * 0.5, MAX_PULL)
      if (pulled.current < TRIGGER && next >= TRIGGER) haptic.tap()
      pulled.current = next
      setPull(next)
    }
    function onEnd() {
      start.current = null
      const ready = pulled.current >= TRIGGER
      pulled.current = 0
      setPull(0)
      if (ready) setSpinning(true)
    }
    window.addEventListener('touchstart', onStart, { passive: true })
    window.addEventListener('touchmove', onMove, { passive: true })
    window.addEventListener('touchend', onEnd)
    window.addEventListener('touchcancel', onEnd)
    return () => {
      window.removeEventListener('touchstart', onStart)
      window.removeEventListener('touchmove', onMove)
      window.removeEventListener('touchend', onEnd)
      window.removeEventListener('touchcancel', onEnd)
    }
  }, [spinning])

  // Обновляем и крутим, пока не вернутся все запросы
  useEffect(() => {
    if (!spinning) return
    const startedAt = Date.now()
    let timer: number | undefined
    function finish() {
      if (timer !== undefined) window.clearTimeout(timer)
      const wait = Math.max(0, MIN_SPIN_MS - (Date.now() - startedAt))
      timer = window.setTimeout(() => setSpinning(false), wait)
    }
    const unsubscribe = subscribePending(() => {
      if (pendingCount() === 0) finish()
    })
    const limit = window.setTimeout(() => setSpinning(false), MAX_SPIN_MS)
    refreshAll()
    // Экраны начинают запросы после отрисовки; если не начали, просто докручиваем минимум
    const check = window.setTimeout(() => {
      if (pendingCount() === 0) finish()
    }, 150)
    return () => {
      unsubscribe()
      window.clearTimeout(limit)
      window.clearTimeout(check)
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [spinning])

  const visible = spinning || pull > 8
  if (!visible) return null
  const progress = spinning ? 1 : Math.min(pull / TRIGGER, 1)
  return (
    <div
      className="refresher"
      aria-live="polite"
      aria-label={spinning ? 'Обновляем' : undefined}
      style={{
        transform: `translateY(${spinning ? TRIGGER * 0.6 : pull * 0.6}px) rotate(${(1 - progress) * -90}deg)`,
        opacity: progress,
      }}
    >
      <BrandMark size={28} spinning={spinning} />
    </div>
  )
}

/** Плашка, пока сервер недоступен: экраны показывают то, что успели загрузить. */
export function OfflineBanner() {
  const online = useOnline()
  if (online) return null
  return (
    <div className="offline-banner" role="status">
      <Icon name="alert" />
      <span>
        Нет связи с сервером
        <small>Показываем то, что успели загрузить</small>
      </span>
      <button type="button" onClick={refreshAll}>
        Повторить
      </button>
    </div>
  )
}
