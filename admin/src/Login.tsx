import { useEffect, useRef, useState } from 'react'
import { ApiError, get, post, type Session, type TelegramLogin } from './api'

declare global {
  interface Window {
    onTelegramAuth?: (user: TelegramLogin) => void
  }
}

// Пока админ не нажал «Да» в боте, спрашиваем состояние входа раз в 2 секунды
const POLL_MS = 2000

type Props = {
  session: Session | null
  onSession: (session: Session) => void
}

export default function Login({ session, onSession }: Props) {
  const widget = useRef<HTMLDivElement>(null)
  const [botName, setBotName] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const pending = session?.state === 'pending'

  useEffect(() => {
    get<{ bot_username: string }>('/admin/auth/config')
      .then((config) => setBotName(config.bot_username))
      .catch(() => setError('Не удалось связаться с сервером. Обновите страницу.'))
  }, [])

  // Виджет Telegram — это их скрипт, который рисует кнопку и вызывает onTelegramAuth
  useEffect(() => {
    const box = widget.current
    if (!botName || !box || pending) return
    window.onTelegramAuth = (user) => {
      setError(null)
      post<Session>('/admin/auth/telegram', user)
        .then(onSession)
        .catch((reason: unknown) => {
          if (reason instanceof ApiError && reason.status === 403) setError('Этот аккаунт не админ Trenio.')
          else setError(reason instanceof Error ? reason.message : 'Не получилось войти')
        })
    }
    const script = document.createElement('script')
    script.src = 'https://telegram.org/js/telegram-widget.js?22'
    script.async = true
    script.dataset.telegramLogin = botName
    script.dataset.size = 'large'
    script.dataset.radius = '14'
    script.dataset.onauth = 'onTelegramAuth(user)'
    script.dataset.requestAccess = 'write'
    box.replaceChildren(script)
    return () => {
      box.replaceChildren()
      delete window.onTelegramAuth
    }
  }, [botName, pending, onSession])

  useEffect(() => {
    if (!pending) return
    const timer = window.setInterval(() => {
      get<Session>('/admin/auth/session')
        .then(onSession)
        .catch(() => undefined)
    }, POLL_MS)
    return () => window.clearInterval(timer)
  }, [pending, onSession])

  return (
    <div className="center">
      <section className="glass login" aria-labelledby="login-title">
        <span className="logo-mark" aria-hidden="true" style={{ width: 48, height: 48, borderRadius: 16 }} />
        <h1 id="login-title" style={{ margin: 0, fontSize: 26, fontWeight: 600 }}>
          Админка Trenio
        </h1>
        {pending ? (
          <>
            <div className="spinner" aria-hidden="true" />
            <p style={{ margin: 0 }}>
              Подтвердите вход в боте: там сообщение «Вход в веб-админку Trenio» с кнопкой
              «Да, это я».
            </p>
            <p className="muted small" style={{ margin: 0 }}>
              Запрос действует 10 минут. Если сообщения нет, проверьте, что бот не заблокирован.
            </p>
          </>
        ) : (
          <>
            <p className="muted" style={{ margin: 0 }}>
              Войдите через Telegram. После этого в бот придёт сообщение для подтверждения
              входа.
            </p>
            {session?.state === 'denied' && <p className="notice">Вход отклонён в боте.</p>}
            {session?.state === 'expired' && (
              <p className="notice">Вход завершён или устарел. Войдите заново.</p>
            )}
            <div ref={widget} style={{ minHeight: 48 }} />
          </>
        )}
        {error && (
          <p className="notice" role="alert" style={{ color: 'var(--red)' }}>
            {error}
          </p>
        )}
      </section>
    </div>
  )
}
