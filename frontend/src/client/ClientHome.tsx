import { useEffect, useState } from 'react'

import {
  errorText,
  fetchMyBookings,
  fetchMyTrainers,
  finishTour,
  type Booking,
  type ClientTrainer,
} from '../api'
import { nextBooking } from '../calendar'
import { dateTime } from '../format'
import { haptic } from '../telegram'
import { CLIENT_TOUR, type ClientTab as Tab } from '../tour'
import Icon, { type IconName } from '../ui/icons'
import { TrainerAvatar } from '../ui/Avatar'
import { EmptyState, ErrorText, PageHeader, Row, Section, SkeletonList } from '../ui/kit'
import { MainButton } from '../ui/native'
import NextSession from '../ui/NextSession'
import { RulesGate } from '../ui/Rules'
import Screen from '../ui/Screen'
import Tour from '../ui/Tour'
import BookTrainer from './BookTrainer'
import ClientProfile from './ClientProfile'
import MyBookings from './MyBookings'
import MyPackages from './MyPackages'
import { useRefreshKey } from '../sync'

const TABS: readonly (readonly [Tab, string, IconName])[] = [
  ['book', 'Запись', 'calendar'],
  ['bookings', 'Мои записи', 'list'],
  ['packages', 'Блоки', 'ticket'],
  ['profile', 'Профиль', 'user'],
]

type Props = {
  // Есть, когда человек ещё и тренер
  onSwitchToTrainer?: () => void
  // false — при входе показываем вводный тур
  tourDone: boolean
  onTourDone: () => void
}

export default function ClientHome({ onSwitchToTrainer, tourDone, onTourDone }: Props) {
  const [tab, setTab] = useState<Tab>('book')
  const [touring, setTouring] = useState(!tourDone)
  const [trainers, setTrainers] = useState<ClientTrainer[] | null>(null)
  // Выбранный тренер, когда их несколько
  const [opened, setOpened] = useState<ClientTrainer | null>(null)
  const [booked, setBooked] = useState<Booking | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Ближайшее занятие для карточки наверху вкладки «Запись»
  const [next, setNext] = useState<Booking | null>(null)
  const refreshKey = useRefreshKey()

  useEffect(() => {
    fetchMyTrainers()
      .then(setTrainers)
      .catch((err: unknown) => setError(errorText(err)))
  }, [refreshKey])

  useEffect(() => {
    // Карточка необязательная: если не загрузилась, просто не показываем
    fetchMyBookings()
      .then((items) => setNext(nextBooking(items, new Date())))
      .catch(() => setNext(null))
  }, [booked, refreshKey])

  function open(next: Tab) {
    if (next !== tab) haptic.select()
    setTab(next)
    window.scrollTo(0, 0)
  }

  function startTour() {
    setOpened(null)
    setTouring(true)
  }

  function endTour() {
    setTouring(false)
    onTourDone()
    // Не сохранилось — покажем ещё раз при следующем входе, не страшно
    finishTour('client').catch(() => {})
  }

  function onBooked(booking: Booking) {
    setOpened(null)
    setBooked(booking)
  }

  // Новые или изменённые правила тренера показываем до всего остального
  const pending = trainers?.find((trainer) => trainer.rules_pending)
  if (pending) {
    return (
      <RulesGate
        key={pending.id}
        trainer={pending}
        onAccepted={(accepted) =>
          setTrainers(
            (current) =>
              current?.map((trainer) => (trainer.id === accepted.id ? accepted : trainer)) ?? null,
          )
        }
      />
    )
  }

  return (
    <>
      {tab === 'book' && (
        <BookTab
          trainers={trainers}
          error={error}
          next={next}
          onNext={() => open('bookings')}
          onOpen={setOpened}
          onBooked={onBooked}
        />
      )}
      {tab === 'bookings' && <MyBookings onBook={() => open('book')} />}
      {tab === 'packages' && <MyPackages />}
      {tab === 'profile' && (
        <ClientProfile
          trainers={trainers}
          onSwitchToTrainer={onSwitchToTrainer}
          onStartTour={startTour}
        />
      )}
      {opened && (
        <Screen
          title={opened.display_name}
          subtitle={opened.address ?? undefined}
          avatar={<TrainerAvatar trainer={opened} size="md" />}
          onBack={() => setOpened(null)}
        >
          <BookTrainer trainer={opened} onBooked={onBooked} />
        </Screen>
      )}
      {booked && (
        <BookedScreen
          booking={booked}
          onDone={() => {
            setBooked(null)
            open('bookings')
          }}
        />
      )}
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
      {/* Тур ждёт, пока клиент примет правила тренера: они показываются выше вместо вкладок */}
      {touring && trainers !== null && (
        <Tour
          steps={CLIENT_TOUR}
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

type BookTabProps = {
  trainers: ClientTrainer[] | null
  error: string | null
  next: Booking | null
  onNext: () => void
  onOpen: (trainer: ClientTrainer) => void
  onBooked: (booking: Booking) => void
}

function BookTab({ trainers, error, next, onNext, onOpen, onBooked }: BookTabProps) {
  const nextCard = next && (
    <NextSession
      booking={next}
      viewer="client"
      timezone={next.trainer.timezone}
      now={new Date()}
      onOpen={onNext}
    />
  )
  if (trainers === null) {
    return (
      <>
        <PageHeader title="Запись" brand />
        {error ? <ErrorText>{error}</ErrorText> : <SkeletonList rows={2} />}
      </>
    )
  }
  if (trainers.length === 0) {
    return (
      <EmptyState
        icon="calendar"
        title="Нет тренеров"
        text="Попросите у тренера ссылку-приглашение и откройте её в Telegram."
      />
    )
  }
  // Один тренер — сразу его окошки, без лишнего шага
  if (trainers.length === 1) {
    const [trainer] = trainers
    return (
      <>
        <PageHeader
          title={trainer.display_name}
          subtitle={trainer.address ?? undefined}
          leading={<TrainerAvatar trainer={trainer} size="md" />}
          brand
        />
        {nextCard}
        <BookTrainer trainer={trainer} onBooked={onBooked} />
      </>
    )
  }
  return (
    <>
      <PageHeader title="Запись" subtitle="Выберите тренера." brand />
      {nextCard}
      <Section>
        {trainers.map((trainer) => (
          <Row
            key={trainer.id}
            title={trainer.display_name}
            subtitle={trainer.address ?? undefined}
            leading={<TrainerAvatar trainer={trainer} />}
            chevron
            onClick={() => onOpen(trainer)}
          />
        ))}
      </Section>
    </>
  )
}

function BookedScreen({ booking, onDone }: { booking: Booking; onDone: () => void }) {
  const pending = booking.status === 'pending'
  const when = dateTime(booking.starts_at, booking.trainer.timezone)
  return (
    <Screen title="Готово" onBack={onDone}>
      <EmptyState
        icon="check"
        title={pending ? 'Заявка отправлена' : 'Вы записаны'}
        text={
          pending
            ? `${booking.service.name}, ${when}. Тренер подтвердит запись, статус будет в «Моих записях».`
            : `${booking.service.name}, ${when}${booking.address ? `, ${booking.address}` : ''}.`
        }
      />
      <MainButton text="Хорошо" onClick={onDone} />
    </Screen>
  )
}
