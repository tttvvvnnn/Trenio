import { useCallback, useEffect, useState } from 'react'
import { ApiError, get } from './api'

// Данные экрана обновляются раз в минуту: «живая» админка без WebSocket
const REFRESH_MS = 60_000

export type Loaded<T> = {
  data: T | null
  error: string | null
  reload: () => void
  updatedAt: Date | null
}

export function useData<T>(path: string, onUnauthorized: () => void): Loaded<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)
  const [tick, setTick] = useState(0)

  const reload = useCallback(() => setTick((value) => value + 1), [])

  useEffect(() => {
    let alive = true
    get<T>(path)
      .then((value) => {
        if (!alive) return
        setData(value)
        setError(null)
        setUpdatedAt(new Date())
      })
      .catch((reason: unknown) => {
        if (!alive) return
        if (reason instanceof ApiError && reason.status === 401) onUnauthorized()
        else setError(reason instanceof Error ? reason.message : 'Ошибка загрузки')
      })
    const timer = window.setTimeout(reload, REFRESH_MS)
    return () => {
      alive = false
      window.clearTimeout(timer)
    }
  }, [path, tick, reload, onUnauthorized])

  return { data, error, reload, updatedAt }
}
