import { useState } from 'react'

import type { Trainer } from '../api'
import Calendar from './Calendar'
import Days from './Days'
import ProfileForm from './ProfileForm'
import Services from './Services'
import WeekTemplate from './WeekTemplate'

const TABS = [
  ['calendar', 'Окошки'],
  ['services', 'Услуги'],
  ['week', 'Неделя'],
  ['days', 'Дни'],
  ['profile', 'Профиль'],
] as const

type Tab = (typeof TABS)[number][0]

type Props = {
  trainer: Trainer
  onTrainerChange: (trainer: Trainer) => void
}

export default function TrainerHome({ trainer, onTrainerChange }: Props) {
  const [tab, setTab] = useState<Tab>('calendar')

  return (
    <>
      <nav className="tabs">
        {TABS.map(([value, title]) => (
          <button
            key={value}
            type="button"
            className={value === tab ? 'tab active' : 'tab'}
            onClick={() => setTab(value)}
          >
            {title}
          </button>
        ))}
      </nav>
      {tab === 'calendar' && (
        <Calendar timezone={trainer.timezone} onGoToSetup={() => setTab('week')} />
      )}
      {tab === 'services' && <Services />}
      {tab === 'week' && <WeekTemplate />}
      {tab === 'days' && <Days timezone={trainer.timezone} />}
      {tab === 'profile' && <ProfileForm trainer={trainer} onSaved={onTrainerChange} />}
    </>
  )
}
