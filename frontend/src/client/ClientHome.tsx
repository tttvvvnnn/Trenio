import { useEffect, useState } from 'react'

import { fetchMyTrainers, type Booking, type ClientTrainer } from '../api'
import { dateTime } from '../format'
import { haptic } from '../telegram'
import Icon, { type IconName } from '../ui/icons'
import { EmptyState, ErrorText, PageHeader, Row, Section, SkeletonList } from '../ui/kit'
import { MainButton } from '../ui/native'
import { RulesGate, RulesScreen } from '../ui/Rules'
import Screen from '../ui/Screen'
import BookTrainer from './BookTrainer'
import MyBookings from './MyBookings'
import MyPackages from './MyPackages'

type Tab = 'book' | 'bookings' | 'packages'

const TABS: readonly (readonly [Tab, string, IconName])[] = [
  ['book', 'Запись', 'calendar'],
  ['bookings', 'Мои записи', 'list'],
  ['packages', 'Блоки', 'ticket'],
]

type Props = {
  // Есть, когда человек ещё и тренер
  onSwitchToTrainer?: () => void
}

export default function ClientHome({ onSwitchToTrainer }: Props) {
  const [tab, setTab] = useState<Tab>('book')
  const [trainers, setTrainers] = useState<ClientTrainer[] | null>(null)
  // Выбранный тренер, когда их несколько
  const [opened, setOpened] = useState<ClientTrainer | null>(null)
  const [booked, setBooked] = useState<Booking | null>(null)
  const [rulesOf, setRulesOf] = useState<ClientTrainer | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchMyTrainers()
      .then(setTrainers)
      .catch((err: unknown) => setError(String(err)))
  }, [])

  function open(next: Tab) {
    if (next !== tab) haptic.select()
    setTab(next)
    window.scrollTo(0, 0)
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
  const withRules = trainers?.filter((trainer) => trainer.rules) ?? []

  return (
    <>
      {tab === 'book' && (
        <BookTab trainers={trainers} error={error} onOpen={setOpened} onBooked={onBooked} />
      )}
      {tab === 'book' && withRules.length > 0 && (
        <Section>
          {withRules.map((trainer) => (
            <Row
              key={trainer.id}
              title="Правила занятий"
              subtitle={(trainers?.length ?? 0) > 1 ? trainer.display_name : undefined}
              icon={{ name: 'list', color: 'var(--c-warning)' }}
              chevron
              onClick={() => setRulesOf(trainer)}
            />
          ))}
        </Section>
      )}
      {tab === 'bookings' && <MyBookings onBook={() => open('book')} />}
      {onSwitchToTrainer && tab !== 'packages' && (
        <Section footer="Ваше расписание и клиенты остаются в профиле тренера.">
          <Row
            title="Профиль тренера"
            icon={{ name: 'user', color: 'var(--c-violet)' }}
            chevron
            onClick={onSwitchToTrainer}
          />
        </Section>
      )}
      {tab === 'packages' && <MyPackages />}
      {opened && (
        <Screen
          title={opened.display_name}
          subtitle={opened.address ?? undefined}
          onBack={() => setOpened(null)}
        >
          <BookTrainer trainer={opened} onBooked={onBooked} />
        </Screen>
      )}
      {rulesOf && <RulesScreen trainer={rulesOf} onBack={() => setRulesOf(null)} />}
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

type BookTabProps = {
  trainers: ClientTrainer[] | null
  error: string | null
  onOpen: (trainer: ClientTrainer) => void
  onBooked: (booking: Booking) => void
}

function BookTab({ trainers, error, onOpen, onBooked }: BookTabProps) {
  if (trainers === null) {
    return (
      <>
        <PageHeader title="Запись" />
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
        <PageHeader title={trainer.display_name} subtitle={trainer.address ?? undefined} />
        <BookTrainer trainer={trainer} onBooked={onBooked} />
      </>
    )
  }
  return (
    <>
      <PageHeader title="Запись" subtitle="Выберите тренера." />
      <Section>
        {trainers.map((trainer) => (
          <Row
            key={trainer.id}
            title={trainer.display_name}
            subtitle={trainer.address ?? undefined}
            icon={{ name: 'user', color: 'var(--c-accent)' }}
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
