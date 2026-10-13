import { useEffect, useState } from 'react'

import { fetchMe, loginWithTelegram, type Me, type Trainer } from './api'
import { setupTelegram } from './telegram'
import ProfileForm from './trainer/ProfileForm'
import TrainerHome from './trainer/TrainerHome'
import { EmptyState } from './ui/kit'

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

  function setTrainer(trainer: Trainer) {
    setState((current) =>
      current.kind === 'ready' ? { kind: 'ready', me: { ...current.me, trainer } } : current,
    )
  }

  const withTabbar = state.kind === 'ready' && state.me.trainer?.onboarded_at != null
  return <main className={withTabbar ? 'app with-tabbar' : 'app'}>{render(state, setTrainer)}</main>
}

function render(state: State, setTrainer: (trainer: Trainer) => void) {
  switch (state.kind) {
    case 'loading':
      return <p className="centered">Загрузка…</p>
    case 'outside-telegram':
      return <p className="centered">Откройте Trenio из Telegram через кнопку в боте.</p>
    case 'error':
      return <p className="centered">Не удалось войти: {state.message}</p>
    case 'ready': {
      const { me } = state
      if (me.trainer === null) {
        return (
          <EmptyState
            icon="calendar"
            title={`Привет, ${me.first_name}!`}
            text="Скоро здесь можно будет записаться к тренеру."
          />
        )
      }
      if (me.trainer.onboarded_at === null) {
        return <ProfileForm trainer={me.trainer} onboarding onSaved={setTrainer} />
      }
      return <TrainerHome trainer={me.trainer} onTrainerChange={setTrainer} />
    }
  }
}
