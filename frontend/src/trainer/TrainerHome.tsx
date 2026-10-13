import { useState } from 'react'

import type { Trainer } from '../api'
import { haptic } from '../telegram'
import Icon, { type IconName } from '../ui/icons'
import Calendar from './Calendar'
import ProfileForm from './ProfileForm'
import Schedule from './Schedule'
import Services from './Services'

const TABS: readonly (readonly [Tab, string, IconName])[] = [
  ['calendar', 'Окошки', 'calendar'],
  ['schedule', 'Расписание', 'clock'],
  ['services', 'Услуги', 'list'],
  ['profile', 'Профиль', 'user'],
]

type Tab = 'calendar' | 'schedule' | 'services' | 'profile'

type Props = {
  trainer: Trainer
  onTrainerChange: (trainer: Trainer) => void
}

export default function TrainerHome({ trainer, onTrainerChange }: Props) {
  const [tab, setTab] = useState<Tab>('calendar')

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
      {tab === 'schedule' && <Schedule timezone={trainer.timezone} />}
      {tab === 'services' && <Services />}
      {tab === 'profile' && <ProfileForm trainer={trainer} onSaved={onTrainerChange} />}
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
