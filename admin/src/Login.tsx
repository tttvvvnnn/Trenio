import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, get, post, type Session, type TelegramLogin } from './api'
import { Wordmark } from './Brand'

// Поля, которые Telegram добавляет к data-auth-url после входа
function loginFromUrl(): TelegramLogin | null {
  const params = new URLSearchParams(window.location.search)
  const id = Number(params.get('id'))
  const authDate = Number(params.get('auth_date'))
  const hash = params.get('hash')
  if (!id || !authDate || !hash) return null
  const optional = (key: string) => params.get(key) ?? undefined
  return {
    id,
    first_name: optional('first_name'),
    last_name: optional('last_name'),
    username: optional('username'),
    photo_url: optional('photo_url'),
    auth_date: authDate,
    hash,
  }
}

// Пока админ не нажал «Да» в боте, спрашиваем состояние входа раз в 2 секунды
const POLL_MS = 2000
// Столько ждём кнопку Telegram, прежде чем подсказать, почему её нет
const WIDGET_WAIT_MS = 6000

type Props = {
  session: Session | null
  onSession: (session: Session) => void
}

export default function Login({ session, onSession }: Props) {
  const widget = useRef<HTMLDivElement>(null)
  const [botName, setBotName] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [noWidget, setNoWidget] = useState(false)
  const pending = session?.state === 'pending'

  useEffect(() => {
    get<{ bot_username: string }>('/admin/auth/config')
      .then((config) => setBotName(config.bot_username))
      .catch(() => setError('Не удалось связаться с сервером. Обновите страницу.'))
  }, [])

  const login = useCallback(
    (user: TelegramLogin) => {
      setError(null)
      post<Session>('/admin/auth/telegram', user)
        .then(onSession)
        .catch((reason: unknown) => {
          if (reason instanceof ApiError && reason.status === 403) setError('Этот аккаунт не админ Trenio.')
          else setError(reason instanceof Error ? reason.message : 'Не получилось войти')
        })
    },
    [onSession],
  )

  // Telegram вернул на страницу с данными входа в адресе: забираем их и убираем из адреса
  useEffect(() => {
    const user = loginFromUrl()
    if (!user) return
    window.history.replaceState(null, '', window.location.pathname + window.location.hash)
    login(user)
  }, [login])

  // Виджет Telegram — это их скрипт, который рисует кнопку. После входа Telegram
  // возвращает на data-auth-url: колбэк data-onauth виджет вызывает через eval, а его
  // запрещает CSP админки
  useEffect(() => {
    const box = widget.current
    if (!botName || !box || pending) return
    const script = document.createElement('script')
    script.src = 'https://telegram.org/js/telegram-widget.js?22'
    script.async = true
    script.dataset.telegramLogin = botName
    script.dataset.size = 'large'
    script.dataset.radius = '14'
    script.dataset.authUrl = window.location.origin + window.location.pathname
    script.dataset.requestAccess = 'write'
    box.replaceChildren(script)
    setNoWidget(false)
    const timer = window.setTimeout(() => setNoWidget(!box.querySelector('iframe')), WIDGET_WAIT_MS)
    return () => {
      window.clearTimeout(timer)
      box.replaceChildren()
    }
  }, [botName, pending])

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
        <h1 id="login-title" style={{ margin: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
          <Wordmark height={44} />
          <span className="logo-tag">веб-админка</span>
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
            {noWidget && (
              <p className="notice small" role="status">
                Кнопка Telegram не загрузилась. Обычно её блокирует расширение браузера или сеть: попробуйте окно
                инкогнито. Ещё проверьте, что домен админки указан у бота @{botName} в @BotFather через /setdomain.
              </p>
            )}
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
