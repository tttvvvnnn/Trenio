import { useEffect, useState } from 'react'

import {
  fetchMe,
  fetchReminders,
  fetchSubscription,
  type Promo,
  type ReminderPrefs,
  type Subscription as Sub,
  type Trainer,
} from '../api'
import { timezoneOptions } from '../format'
import { useRefreshKey } from '../sync'
import { homeScreen } from '../telegram'
import { TOUR_REPLAY } from '../tour'
import Avatar from '../ui/Avatar'
import { Row, Section } from '../ui/kit'
import { AccountDataScreen } from '../ui/Privacy'
import { PromoSection } from '../ui/Promo'
import ReminderSettings from '../ui/ReminderSettings'
import { bookingSettingsLine, reminderLine, subscriptionLine } from '../settings'
import Screen from '../ui/Screen'
import BookingSettings from './BookingSettings'
import InviteTrainer from './InviteTrainer'
import ProfileForm from './ProfileForm'
import RulesEditor from './RulesEditor'
import Subscription from './Subscription'

type Props = {
  trainer: Trainer
  onSaved: (trainer: Trainer) => void
  // Услуги и шаблоны блоков: отдельный экран
  onOpenServices: () => void
  // Есть только у админа
  onOpenAdmin?: () => void
  // Есть, когда тренер сам записан к другому тренеру
  onSwitchToClient?: () => void
  // Запустить вводный тур заново
  onStartTour: () => void
  // Предложение от автора внизу Профиля; null — выключено
  promo: Promo | null
  // Открыли кнопкой из уведомления: сразу на приглашения тренеров или подписку
  initialOpened?: 'invite' | 'subscription'
}

type Opened =
  | 'edit'
  | 'booking'
  | 'rules'
  | 'reminders'
  | 'invite'
  | 'subscription'
  | 'account'
  | null

/** Профиль тренера: кто вы, настройки работы, уведомления и остальное. */
export default function TrainerProfile({
  trainer,
  onSaved,
  onOpenServices,
  onOpenAdmin,
  onSwitchToClient,
  onStartTour,
  promo,
  initialOpened,
}: Props) {
  const [opened, setOpened] = useState<Opened>(initialOpened ?? null)
  const [avatar, setAvatar] = useState<string | null>(null)
  const [reminders, setReminders] = useState<ReminderPrefs | null>(null)
  const [sub, setSub] = useState<Sub | null>(null)
  const [onHomeScreen, setOnHomeScreen] = useState(true)
  const refreshKey = useRefreshKey()

  // Фото и напоминания перечитываем, когда закрылся экран, где их могли поменять
  useEffect(() => {
    if (opened !== null) return
    fetchMe()
      .then((me) => setAvatar(me.avatar_url))
      .catch(() => {})
    fetchReminders()
      .then((all) => setReminders(all.trainer))
      .catch(() => {})
    fetchSubscription()
      .then(setSub)
      .catch(() => {})
  }, [opened, refreshKey])

  useEffect(() => {
    if (homeScreen.supported()) void homeScreen.added().then(setOnHomeScreen)
  }, [])

  function saved(updated: Trainer) {
    setOpened(null)
    onSaved(updated)
  }

  const zone = timezoneOptions(trainer.timezone).find(([value]) => value === trainer.timezone)
  const place = [trainer.address, zone?.[1] ?? trainer.timezone].filter(Boolean).join(' · ')

  return (
    <>
      <div className="profile-head">
        <Avatar name={trainer.display_name} url={avatar} seed={trainer.id} size="md" />
        <div>
          <h1>{trainer.display_name}</h1>
          <p>{place}</p>
        </div>
        <button type="button" className="pill-button" onClick={() => setOpened('edit')}>
          Изменить
        </button>
      </div>
      {sub && (
        <Section title="Подписка">
          <Row
            {...subscriptionLine(sub, trainer.timezone)}
            icon={{ name: 'star', color: 'var(--c-warning)' }}
            chevron
            onClick={() => setOpened('subscription')}
          />
        </Section>
      )}
      <Section title="Работа">
        <Row
          title="Услуги и блоки"
          tourId="services"
          icon={{ name: 'ticket', color: 'var(--c-violet)' }}
          chevron
          onClick={onOpenServices}
        />
        <Row
          title="Правила занятий"
          subtitle={trainer.rules ? 'Клиент соглашается перед первой записью' : 'Не заполнены'}
          icon={{ name: 'list', color: 'var(--c-warning)' }}
          chevron
          onClick={() => setOpened('rules')}
        />
        <Row
          title="Как клиенты записываются"
          subtitle={bookingSettingsLine(trainer)}
          icon={{ name: 'check', color: 'var(--c-success)' }}
          chevron
          onClick={() => setOpened('booking')}
        />
      </Section>
      <Section title="Уведомления">
        <Row
          title="Напоминания"
          subtitle={reminders ? reminderLine(reminders, 'trainer') : undefined}
          icon={{ name: 'bell', color: 'var(--c-warning)' }}
          chevron
          onClick={() => setOpened('reminders')}
        />
      </Section>
      <Section title="Ещё">
        <Row
          title="Пригласить тренера"
          subtitle="Личная ссылка для коллег"
          icon={{ name: 'share', color: 'var(--c-violet)' }}
          chevron
          onClick={() => setOpened('invite')}
        />
        {!onHomeScreen && (
          <Row
            title="Trenio на экране телефона"
            subtitle="Открывать без поиска бота"
            icon={{ name: 'smartphone', color: 'var(--c-accent)' }}
            chevron
            onClick={() => {
              homeScreen.add()
              // Проверим ещё раз, когда пользователь вернётся из системного окна
              window.setTimeout(() => void homeScreen.added().then(setOnHomeScreen), 3000)
            }}
          />
        )}
        <Row
          title="Как пользоваться"
          icon={{ name: 'help', color: 'var(--c-success)' }}
          chevron
          tourId={TOUR_REPLAY}
          onClick={onStartTour}
        />
        {onSwitchToClient && (
          <Row
            title="Профиль клиента"
            subtitle="Ваши записи к другим тренерам"
            icon={{ name: 'calendar', color: 'var(--c-accent)' }}
            chevron
            onClick={onSwitchToClient}
          />
        )}
        {onOpenAdmin && (
          <Row
            title="Админ-панель"
            icon={{ name: 'users', color: 'var(--c-planned)' }}
            chevron
            onClick={onOpenAdmin}
          />
        )}
        <Row
          title="Данные и аккаунт"
          icon={{ name: 'shield', color: 'var(--c-hint)' }}
          chevron
          onClick={() => setOpened('account')}
        />
      </Section>
      <PromoSection promo={promo} />
      {opened === 'edit' && (
        <Screen title="Мой профиль" onBack={() => setOpened(null)}>
          <ProfileForm trainer={trainer} onSaved={saved} />
        </Screen>
      )}
      {opened === 'booking' && (
        <BookingSettings trainer={trainer} onBack={() => setOpened(null)} onSaved={saved} />
      )}
      {opened === 'rules' && (
        <RulesEditor trainer={trainer} onSaved={saved} onBack={() => setOpened(null)} />
      )}
      {opened === 'reminders' && (
        <Screen title="Напоминания" onBack={() => setOpened(null)}>
          <ReminderSettings role="trainer" />
        </Screen>
      )}
      {opened === 'subscription' && (
        <Subscription timezone={trainer.timezone} onBack={() => setOpened(null)} />
      )}
      {opened === 'invite' && (
        <InviteTrainer timezone={trainer.timezone} onBack={() => setOpened(null)} />
      )}
      {opened === 'account' && <AccountDataScreen trainer onBack={() => setOpened(null)} />}
    </>
  )
}
