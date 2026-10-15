import { useSyncExternalStore } from 'react'

import { errorText } from './api'
import { emitRefresh } from './sync'

/*
 * «Отменить» вместо «Вы уверены?». Экран сразу показывает результат, а внизу
 * 5 секунд висит плашка с кнопкой «Отменить».
 *
 * commit — то, что уходит на сервер, когда время вышло: так удаление можно вернуть
 * без запроса. Если приложение свернули или начали новое действие, commit
 * отправляется сразу, чтобы ничего не потерялось.
 * undo — вернуть экран как было (и, если действие уже ушло на сервер, вернуть там).
 */

export const UNDO_MS = 5000

export type UndoAction = {
  text: string
  commit?: () => Promise<unknown>
  undo: () => unknown
  // Не получилось отправить commit: экран уже вернули через undo
  onError?: (message: string) => void
}

export type Toast = { id: number; text: string; undoable: boolean }

let current: { action: UndoAction; timer: number } | null = null
let toast: Toast | null = null
let nextId = 1
let hideTimer: number | undefined
const listeners = new Set<() => void>()

function show(next: Toast | null, hideAfter?: number) {
  toast = next
  window.clearTimeout(hideTimer)
  if (next && hideAfter) hideTimer = window.setTimeout(() => show(null), hideAfter)
  for (const listener of listeners) listener()
}

function commit(action: UndoAction) {
  if (!action.commit) return
  action
    .commit()
    // Экраны перечитают данные: вдруг кто-то успел загрузить их до удаления
    .then(() => emitRefresh())
    .catch((error: unknown) => {
      action.undo()
      const message = errorText(error)
      action.onError?.(message)
      show({ id: nextId++, text: `Не получилось: ${message}`, undoable: false }, 4000)
    })
}

// Отправить отложенное прямо сейчас
export function flushUndo() {
  if (!current) return
  const { action, timer } = current
  current = null
  window.clearTimeout(timer)
  show(null)
  commit(action)
}

export function withUndo(action: UndoAction) {
  flushUndo()
  const timer = window.setTimeout(() => {
    current = null
    commit(action)
    show(null)
  }, UNDO_MS)
  current = { action, timer }
  show({ id: nextId++, text: action.text, undoable: true })
}

export function undoLast() {
  if (!current) return
  const { action, timer } = current
  current = null
  window.clearTimeout(timer)
  show(null)
  // undo может сам ходить на сервер, например вернуть прежнюю отметку
  Promise.resolve(action.undo()).catch((error: unknown) => {
    show({ id: nextId++, text: `Не получилось: ${errorText(error)}`, undoable: false }, 4000)
  })
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function useToast(): Toast | null {
  return useSyncExternalStore(subscribe, () => toast)
}

// Свернули или закрыли приложение: таймер может не дожить, отправляем сразу
if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') flushUndo()
  })
  window.addEventListener('pagehide', flushUndo)
}
