import { useState } from 'react'

import type { Trainer } from '../api'
import { haptic } from '../telegram'
import Icon, { type IconName } from '../ui/icons'
import Screen from '../ui/Screen'
import Calendar from './Calendar'
import Clients from './Clients'
import Finance from './Finance'
import ProfileForm from './ProfileForm'
import Schedule from './Schedule'
import Services from './Services'

const TABS: readonly (readonly [Tab, string, IconName])[] = [
  ['calendar', 'Записи', 'calendar'],
  ['clients', 'Клиенты', 'users'],
  ['schedule', 'Расписание', 'clock'],
  ['finance', 'Финансы', 'wallet'],
  ['profile', 'Профиль', 'user'],
]

type Tab = 'calendar' | 'clients' | 'schedule' | 'finance' | 'profile'

type Props = {
  trainer: Trainer
  onTrainerChange: (trainer: Trainer) => void
  // Есть, когда тренер сам записан к другому тренеру
  onSwitchToClient?: () => void
}

export default function TrainerHome({ trainer, onTrainerChange, onSwitchToClient }: Props) {
  const [tab, setTab] = useState<Tab>('calendar')
  // Услуги и шаблоны блоков открываются из Профиля
  const [services, setServices] = useState(false)

  function open(next: Tab) {
    if (next !== tab) haptic.select()
    setTab(next)
    window.scrollTo(0, 0)
  }

  return (
    <>
      {tab === 'calendar' && (
        <Calendar timezone={trainer.timezone} onGoToSetup={() => open('schedule')} />
      )}
      {tab === 'clients' && <Clients timezone={trainer.timezone} />}
      {tab === 'schedule' && <Schedule timezone={trainer.timezone} />}
      {tab === 'finance' && <Finance timezone={trainer.timezone} />}
      {tab === 'profile' && (
        <ProfileForm
          trainer={trainer}
          onSaved={onTrainerChange}
          onOpenServices={() => setServices(true)}
          onSwitchToClient={onSwitchToClient}
        />
      )}
      {tab === 'profile' && services && (
        <Screen
          title="Услуги"
          subtitle="На них клиенты записываются в окошки."
          onBack={() => setServices(false)}
        >
          <Services embedded />
        </Screen>
      )}
      <nav className="tabbar" aria-label="Разделы">
        {TABS.map(([value, title, icon]) => (
          <button
            key={value}
            type="button"
            className="tab"
            aria-current={value === tab ? 'page' : undefined}
            onClick={() => open(value)}
          >
            <Icon name={icon} />
            {title}
          </button>
        ))}
      </nav>
    </>
  )
}
