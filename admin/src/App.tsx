import { useCallback, useEffect, useState } from 'react'
import { ApiError, get, post, setCsrfToken, type Session } from './api'
import Login from './Login'
import type { Section } from './sections'
import Shell from './Shell'
import Clients from './screens/Clients'
import Money from './screens/Money'
import Soon from './screens/Soon'
import Summary from './screens/Summary'
import System from './screens/System'
import Trainers from './screens/Trainers'

type Auth = { kind: 'loading' } | { kind: 'login'; session: Session | null } | { kind: 'in'; session: Session }

function sectionFromHash(): Section {
  const value = window.location.hash.replace('#/', '')
  const known: Section[] = ['summary', 'trainers', 'clients', 'money', 'broadcasts', 'plans', 'support', 'system']
  return (known as string[]).includes(value) ? (value as Section) : 'summary'
}

export default function App() {
  const [auth, setAuth] = useState<Auth>({ kind: 'loading' })
  const [section, setSection] = useState<Section>(sectionFromHash)

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
    const onHash = () => setSection(sectionFromHash())
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
      <div className="center">
        <div className="spinner" role="status" aria-label="Загрузка" />
      </div>
    )
  }
  if (auth.kind === 'login') return <Login session={auth.session} onSession={accept} />

  const props = { onUnauthorized: signOut }
  return (
    <Shell section={section} name={auth.session.name} onLogout={logout}>
      {section === 'summary' && <Summary {...props} />}
      {section === 'trainers' && <Trainers {...props} />}
      {section === 'clients' && <Clients {...props} />}
      {section === 'money' && <Money {...props} />}
      {section === 'system' && <System {...props} />}
      {(section === 'broadcasts' ||
        section === 'plans' ||
        section === 'support') && <Soon section={section} />}
    </Shell>
  )
}
