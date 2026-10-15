import { useEffect, useState } from 'react'

import { errorText, fetchMe, loginWithTelegram, type Me, type TourRole, type Trainer } from './api'
import ClientHome from './client/ClientHome'
import { setupTelegram } from './telegram'
import ProfileForm from './trainer/ProfileForm'
import TrainerHome from './trainer/TrainerHome'
import BrandMark from './ui/BrandMark'
import { EmptyState } from './ui/kit'
import { ConsentGate } from './ui/Privacy'
import Refresher, { OfflineBanner } from './ui/Refresh'
import RolePicker from './ui/RolePicker'

type State =
  | { kind: 'loading' }
  | { kind: 'outside-telegram' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; me: Me }

export default function App() {
  const [state, setState] = useState<State>({ kind: 'loading' })
  // Тренер, который сам ходит к другому тренеру, выбирает профиль при каждом входе.
  // null — ещё не выбрал
  const [clientMode, setClientMode] = useState<boolean | null>(null)

  useEffect(() => {
    const initData = setupTelegram()
    if (!initData) {
      setState({ kind: 'outside-telegram' })
      return
    }
    loginWithTelegram(initData)
      .then(fetchMe)
      .then((me) => setState({ kind: 'ready', me }))
      .catch((error: unknown) => setState({ kind: 'error', message: errorText(error) }))
  }, [])

  function setTourDone(role: TourRole) {
    setState((current) =>
      current.kind === 'ready'
        ? { kind: 'ready', me: { ...current.me, [`${role}_tour_done`]: true } }
        : current,
    )
  }

  function setConsented() {
    setState((current) =>
      current.kind === 'ready'
        ? { kind: 'ready', me: { ...current.me, consent_required: false } }
        : current,
    )
  }

  function setTrainer(trainer: Trainer) {
    setState((current) =>
      current.kind === 'ready' ? { kind: 'ready', me: { ...current.me, trainer } } : current,
    )
  }

  const view = state.kind === 'ready' ? chooseView(state.me, clientMode) : null
  const withTabbar =
    (view === 'client' || view === 'trainer') &&
    !(state.kind === 'ready' && state.me.consent_required)
  return (
    <main className={withTabbar ? 'app with-tabbar' : 'app'}>
      {state.kind === 'ready' && (
        <>
          <Refresher />
          <OfflineBanner />
        </>
      )}
      {state.kind === 'ready' && state.me.consent_required ? (
        <ConsentGate onAccepted={setConsented} />
      ) : (
        render(state, view, setTrainer, setClientMode, setTourDone)
      )}
    </main>
  )
}

type View = 'client' | 'trainer' | 'onboarding' | 'stranger' | 'choose'

function chooseView(me: Me, clientMode: boolean | null): View {
  if (me.trainer === null) return me.is_client ? 'client' : 'stranger'
  if (me.trainer.onboarded_at === null) return 'onboarding'
  if (!me.is_client) return 'trainer'
  if (clientMode === null) return 'choose'
  return clientMode ? 'client' : 'trainer'
}

function render(
  state: State,
  view: View | null,
  setTrainer: (trainer: Trainer) => void,
  setClientMode: (clientMode: boolean) => void,
  setTourDone: (role: TourRole) => void,
) {
  switch (state.kind) {
    case 'loading':
      return (
        <div className="centered splash" aria-busy="true" aria-label="Загрузка">
          <BrandMark spinning />
        </div>
      )
    case 'outside-telegram':
      return <p className="centered">Откройте Trenio из Telegram через кнопку в боте.</p>
    case 'error':
      return <p className="centered">Не удалось войти: {state.message}</p>
    case 'ready': {
      const { me } = state
      if (view === 'choose') {
        return <RolePicker name={me.first_name} onChoose={setClientMode} />
      }
      if (view === 'client') {
        return (
          <ClientHome
            onSwitchToTrainer={me.trainer ? () => setClientMode(false) : undefined}
            tourDone={me.client_tour_done}
            onTourDone={() => setTourDone('client')}
          />
        )
      }
      if (me.trainer === null) {
        return (
          <EmptyState
            icon="calendar"
            title={`Привет, ${me.first_name}!`}
            text="Чтобы записаться, попросите у тренера ссылку-приглашение и откройте её в Telegram."
          />
        )
      }
      if (view === 'onboarding') {
        return <ProfileForm trainer={me.trainer} onboarding onSaved={setTrainer} />
      }
      return (
        <TrainerHome
          trainer={me.trainer}
          isAdmin={me.is_admin}
          onTrainerChange={setTrainer}
          onSwitchToClient={me.is_client ? () => setClientMode(true) : undefined}
          tourDone={me.trainer_tour_done}
          onTourDone={() => setTourDone('trainer')}
        />
      )
    }
  }
}
