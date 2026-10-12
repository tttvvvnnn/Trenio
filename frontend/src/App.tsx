import { useEffect, useState } from 'react'

import { fetchMe, loginWithTelegram, type Me } from './api'
import { setupTelegram } from './telegram'

type State =
  | { kind: 'loading' }
  | { kind: 'outside-telegram' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; me: Me }

export default function App() {
  const [state, setState] = useState<State>({ kind: 'loading' })

  useEffect(() => {
    const initData = setupTelegram()
    if (!initData) {
      setState({ kind: 'outside-telegram' })
      return
    }
    loginWithTelegram(initData)
      .then(fetchMe)
      .then((me) => setState({ kind: 'ready', me }))
      .catch((error: unknown) => setState({ kind: 'error', message: String(error) }))
  }, [])

  return <main className="screen">{render(state)}</main>
}

function render(state: State) {
  switch (state.kind) {
    case 'loading':
      return <p className="hint">Загрузка…</p>
    case 'outside-telegram':
      return <p className="hint">Откройте Trenio из Telegram через кнопку в боте.</p>
    case 'error':
      return <p className="hint">Не удалось войти: {state.message}</p>
    case 'ready':
      return (
        <>
          <h1>Привет, {state.me.first_name}!</h1>
          <p className="hint">
            {state.me.is_trainer
              ? 'Вы тренер. Скоро здесь появятся расписание и клиенты.'
              : 'Скоро здесь можно будет записаться к тренеру.'}
          </p>
        </>
      )
  }
}
