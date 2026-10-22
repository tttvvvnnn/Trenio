import { useCallback, useEffect, useState } from 'react'
import { ApiError, get, post, setCsrfToken, type Session } from './api'
import { Mark } from './Brand'
import Login from './Login'
import { parseRoute, type Route } from './route'
import Shell from './Shell'
import Broadcasts from './screens/Broadcasts'
import Clients from './screens/Clients'
import Money from './screens/Money'
import Plans from './screens/Plans'
import Support from './screens/Support'
import Summary from './screens/Summary'
import System from './screens/System'
import TrainerProfile from './screens/TrainerProfile'
import Trainers from './screens/Trainers'

type Auth = { kind: 'loading' } | { kind: 'login'; session: Session | null } | { kind: 'in'; session: Session }

export default function App() {
  const [auth, setAuth] = useState<Auth>({ kind: 'loading' })
  const [route, setRoute] = useState<Route>(() => parseRoute())

  const accept = useCallback((session: Session) => {
    if (session.state === 'active') {
      setCsrfToken(session.csrf_token)
      setAuth({ kind: 'in', session })
    } else {
      setCsrfToken(null)
      setAuth({ kind: 'login', session })
    }
  }, [])

  const signOut = useCallback(() => {
    setCsrfToken(null)
    setAuth({ kind: 'login', session: null })
  }, [])

  useEffect(() => {
    get<Session>('/admin/auth/session')
      .then(accept)
      .catch((reason: unknown) => {
        if (reason instanceof ApiError && reason.status === 401) signOut()
        else setAuth({ kind: 'login', session: null })
      })
  }, [accept, signOut])

  useEffect(() => {
    const onHash = () => setRoute(parseRoute())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const logout = useCallback(async () => {
    try {
      await post('/admin/auth/logout')
    } finally {
      signOut()
    }
  }, [signOut])

  if (auth.kind === 'loading') {
    return (
      <div className="center" role="status" aria-label="Загрузка">
        <div className="splash">
          <Mark size={56} />
        </div>
      </div>
    )
  }
  if (auth.kind === 'login') return <Login session={auth.session} onSession={accept} />

  const props = { onUnauthorized: signOut }
  const { section } = route
  return (
    <Shell section={section} name={auth.session.name} onLogout={logout}>
      {section === 'summary' && <Summary {...props} />}
      {section === 'trainers' && (route.id ? <TrainerProfile key={route.id} id={route.id} {...props} /> : <Trainers {...props} />)}
      {section === 'clients' && <Clients route={route} {...props} />}
      {section === 'money' && <Money {...props} />}
      {section === 'plans' && <Plans {...props} />}
      {section === 'broadcasts' && <Broadcasts {...props} />}
      {section === 'system' && <System {...props} />}
      {section === 'support' && <Support {...props} />}
    </Shell>
  )
}
