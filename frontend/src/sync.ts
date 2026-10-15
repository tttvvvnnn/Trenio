import { useEffect, useState, useSyncExternalStore } from 'react'

/*
 * Кэш ответов API и общий сигнал «данные обновились».
 *
 * GET-запросы запоминаются, пока приложение открыто. Повторный запрос сразу отдаёт
 * сохранённое и тихо проверяет сервер; если ответ изменился, экраны получают сигнал
 * и перечитывают данные (уже из свежего кэша). Любое изменение (POST, PUT, PATCH,
 * DELETE) помечает весь кэш устаревшим: так не нужно помнить, какие списки оно задевает.
 * Устаревшее показываем, только если сервер недоступен.
 */

// stale — данные устарели после изменения или обновления: годятся, только если сервер недоступен
type Entry = { data: unknown; json: string; at: number; stale: boolean }

// Сразу после загрузки не перепроверяем: иначе каждый сигнал вызывал бы второй запрос
const FRESH_MS = 2000

const cache = new Map<string, Entry>()
const inflight = new Map<string, Promise<unknown>>()
// Номер поколения кэша: ответ, начатый до очистки, не должен вернуть старые данные в кэш
let generation = 0

const listeners = new Set<() => void>()

export function emitRefresh() {
  for (const listener of listeners) listener()
}

export function invalidate() {
  for (const entry of cache.values()) entry.stale = true
  inflight.clear()
  generation += 1
}

// Число растёт по сигналу «данные обновились»: добавьте его в зависимости загрузки экрана
export function useRefreshKey(): number {
  const [key, setKey] = useState(0)
  useEffect(() => {
    const listener = () => setKey((count) => count + 1)
    listeners.add(listener)
    return () => {
      listeners.delete(listener)
    }
  }, [])
  return key
}

/* Сколько запросов в пути: по нему крутится секундомер при обновлении жестом */
let pending = 0
const pendingListeners = new Set<() => void>()

function setPending(delta: number) {
  pending += delta
  for (const listener of pendingListeners) listener()
}

export function trackPending<T>(promise: Promise<T>): Promise<T> {
  setPending(1)
  return promise.finally(() => setPending(-1))
}

export function pendingCount(): number {
  return pending
}

export function subscribePending(listener: () => void): () => void {
  pendingListeners.add(listener)
  return () => {
    pendingListeners.delete(listener)
  }
}

/* Связь с сервером: false, если последний запрос не дошёл */
let online = true
const onlineListeners = new Set<() => void>()

export function setOnline(value: boolean) {
  if (online === value) return
  online = value
  for (const listener of onlineListeners) listener()
}

function subscribeOnline(listener: () => void): () => void {
  onlineListeners.add(listener)
  return () => {
    onlineListeners.delete(listener)
  }
}

export function useOnline(): boolean {
  return useSyncExternalStore(subscribeOnline, () => online)
}

// GET через кэш. load делает настоящий запрос
export function cachedGet<T>(key: string, load: () => Promise<T>): Promise<T> {
  const entry = cache.get(key)
  if (entry && !entry.stale) {
    if (Date.now() - entry.at > FRESH_MS) {
      revalidate(key, load)
    }
    return Promise.resolve(entry.data as T)
  }
  return fetchInto(key, load).catch((error: unknown) => {
    // Нет связи: лучше показать устаревшее, чем ошибку. Плашку «нет связи» покажет App
    if (entry && isNetworkError(error)) return entry.data as T
    throw error
  })
}

function isNetworkError(error: unknown): boolean {
  return error instanceof Error && 'status' in error && error.status === 0
}

function fetchInto<T>(key: string, load: () => Promise<T>): Promise<T> {
  const running = inflight.get(key)
  if (running) return running as Promise<T>
  const started = generation
  const promise = trackPending(load())
    .then((data) => {
      if (generation === started) {
        cache.set(key, { data, json: JSON.stringify(data), at: Date.now(), stale: false })
      }
      return data
    })
    .finally(() => {
      if (inflight.get(key) === promise) inflight.delete(key)
    })
  inflight.set(key, promise)
  return promise
}

function revalidate<T>(key: string, load: () => Promise<T>) {
  if (inflight.has(key)) return
  const before = cache.get(key)?.json
  fetchInto(key, load)
    .then(() => {
      const after = cache.get(key)?.json
      if (after !== undefined && after !== before) emitRefresh()
    })
    // Фоновая проверка: экран уже показывает сохранённое, ошибку видно по плашке связи
    .catch(() => {})
}
