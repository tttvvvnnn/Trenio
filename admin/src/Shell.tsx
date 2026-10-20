import { useState, type ReactNode } from 'react'
import { Wordmark } from './Brand'
import { SECTIONS, type Section } from './sections'
import { applyTheme, savedTheme, type Theme } from './theme'

type Props = {
  section: Section
  name: string
  onLogout: () => void
  children: ReactNode
}

export default function Shell({ section, name, onLogout, children }: Props) {
  const [theme, setTheme] = useState<Theme>(savedTheme)

  const choose = (value: Theme) => {
    setTheme(value)
    applyTheme(value)
  }

  return (
    <>
      <header className="header">
        <a className="logo" href="#/summary" aria-label="trenio, админка: на сводку">
          <Wordmark height={26} />
          <span className="logo-tag">админка</span>
        </a>
        <nav className="glass pill-nav" aria-label="Разделы">
          {SECTIONS.map((item) => (
            <a
              key={item.id}
              href={`#/${item.id}`}
              aria-current={item.id === section ? 'page' : undefined}
            >
              {item.label}
            </a>
          ))}
        </nav>
        <div className="header-right">
          <span className="live" title="Данные обновляются раз в минуту">
            <span className="dot" aria-hidden="true" />
            live
          </span>
          <div className="glass segmented" role="group" aria-label="Тема">
            <button type="button" aria-pressed={theme === 'light'} onClick={() => choose('light')}>
              <SunIcon />
              Светлая
            </button>
            <button type="button" aria-pressed={theme === 'dark'} onClick={() => choose('dark')}>
              <MoonIcon />
              Тёмная
            </button>
          </div>
          <button type="button" className="btn secondary small" onClick={onLogout} title={name}>
            Выйти
          </button>
        </div>
      </header>
      <main className="main">{children}</main>
    </>
  )
}

function SunIcon() {
  return (
    <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    </svg>
  )
}
