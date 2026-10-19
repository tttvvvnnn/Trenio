import { useState } from 'react'

import { finishTour, type Trainer } from '../api'
import { takeLink } from '../deeplink'
import { usePromo } from '../promo'
import { haptic } from '../telegram'
import { TRAINER_TOUR, type TrainerTab as Tab } from '../tour'
import Icon, { type IconName } from '../ui/icons'
import AdminPanel from '../admin/AdminPanel'
import Screen from '../ui/Screen'
import { PromoCard } from '../ui/Promo'
import Tour from '../ui/Tour'
import Calendar from './Calendar'
import Clients from './Clients'
import Finance from './Finance'
import HomeScreenTip from './HomeScreenTip'
import Schedule from './Schedule'
import Services from './Services'
import TrainerLink from './TrainerLink'
import TrainerProfile from './TrainerProfile'

const TABS: readonly (readonly [Tab, string, IconName])[] = [
  ['calendar', 'Записи', 'calendar'],
  ['clients', 'Клиенты', 'users'],
  ['schedule', 'Расписание', 'clock'],
  ['finance', 'Финансы', 'wallet'],
  ['profile', 'Профиль', 'user'],
]

type Props = {
  trainer: Trainer
  // Админу в Профиле доступна админ-панель
  isAdmin?: boolean
  onTrainerChange: (trainer: Trainer) => void
  // Есть, когда тренер сам записан к другому тренеру
  onSwitchToClient?: () => void
  // false — при входе показываем вводный тур
  tourDone: boolean
  onTourDone: () => void
}

export default function TrainerHome({
  trainer,
  isAdmin = false,
  onTrainerChange,
  onSwitchToClient,
  tourDone,
  onTourDone,
}: Props) {
  // Открыли кнопкой из уведомления: сразу на нужную запись или клиента
  const [link] = useState(() => takeLink('trainer'))
  // Экран Профиля, на который ведёт кнопка из уведомления
  const profileScreen =
    link?.tab === 'referrals' ? 'invite' : link?.tab === 'subscription' ? 'subscription' : undefined
  const [tab, setTab] = useState<Tab>(
    link?.client !== undefined ? 'clients' : profileScreen ? 'profile' : 'calendar',
  )
  // Тур не перекрывает то, ради чего открыли приложение: покажем при следующем входе
  const [touring, setTouring] = useState(!tourDone && link === null)
  // Услуги и шаблоны блоков открываются из Профиля
  const [services, setServices] = useState(false)
  const [admin, setAdmin] = useState(false)
  const promo = usePromo()

  function open(next: Tab) {
    if (next !== tab) haptic.select()
    setTab(next)
    window.scrollTo(0, 0)
  }

  function startTour() {
    setServices(false)
    setAdmin(false)
    setTouring(true)
  }

  function endTour() {
    setTouring(false)
    onTourDone()
    // Не сохранилось — покажем ещё раз при следующем входе, не страшно
    finishTour('trainer').catch(() => {})
  }

  return (
    <>
      {tab === 'calendar' && (
        <Calendar
          timezone={trainer.timezone}
          onGoToSetup={() => open('schedule')}
          tip={
            <>
              {!touring && <PromoCard promo={promo} />}
              <HomeScreenTip trainer={trainer} />
            </>
          }
        />
      )}
      {tab === 'clients' && <Clients timezone={trainer.timezone} />}
      {tab === 'schedule' && <Schedule timezone={trainer.timezone} />}
      {tab === 'finance' && <Finance timezone={trainer.timezone} />}
      {tab === 'profile' && (
        <TrainerProfile
          trainer={trainer}
          onSaved={onTrainerChange}
          onOpenServices={() => setServices(true)}
          onOpenAdmin={isAdmin ? () => setAdmin(true) : undefined}
          onSwitchToClient={onSwitchToClient}
          onStartTour={startTour}
          promo={promo}
          initialOpened={profileScreen}
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
      {tab === 'profile' && admin && <AdminPanel onBack={() => setAdmin(false)} />}
      {link && <TrainerLink link={link} timezone={trainer.timezone} />}
      <nav className="tabbar" aria-label="Разделы">
        {TABS.map(([value, title, icon]) => (
          <button
            key={value}
            type="button"
            className="tab"
            data-tour={`tab-${value}`}
            aria-current={value === tab ? 'page' : undefined}
            onClick={() => open(value)}
          >
            <Icon name={icon} />
            {title}
          </button>
        ))}
      </nav>
      {touring && (
        <Tour
          steps={TRAINER_TOUR}
          onTab={(next) => {
            setTab(next)
            window.scrollTo(0, 0)
          }}
          onFinish={endTour}
        />
      )}
    </>
  )
}
