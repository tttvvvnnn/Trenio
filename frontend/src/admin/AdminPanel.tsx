import { useEffect, useState } from 'react'

import {
  errorText,
  createTrainerInvite,
  fetchAdminOverview,
  fetchAdminTrainers,
  fetchOpenInvites,
  setTrainerActive,
  type AdminOverview,
  type AdminTrainer,
  type AdminTrainerState,
} from '../api'
import { dateTime, dayOfMonth, longDate, plural, rubles, shortDate } from '../format'
import { confirmAction, haptic, openTelegram, shareLink } from '../telegram'
import { TrainerAvatar } from '../ui/Avatar'
import { AddRow, ErrorText, Row, Section, SkeletonList } from '../ui/kit'
import Screen from '../ui/Screen'
import AdminPromo from './AdminPromo'

// Даты в админке по Москве, как в боте
const TIMEZONE = 'Europe/Moscow'

const STATE: Record<AdminTrainerState, [string, string]> = {
  active: ['работает', 'success'],
  quiet: ['затих', 'warning'],
  not_set_up: ['не настроил', 'alert'],
  disabled: ['отключён', 'cancelled'],
}

// «сегодня», «вчера», «5 дн назад»; null — ещё не заходил
function ago(iso: string | null, now = new Date()): string {
  if (!iso) return 'не заходил'
  const days = Math.floor((now.getTime() - new Date(iso).getTime()) / 86_400_000)
  if (days <= 0) return 'сегодня'
  if (days === 1) return 'вчера'
  return `${days} дн назад`
}

type Props = {
  onBack: () => void
}

/** Админ-панель: общие цифры платформы, тренеры и приглашения. */
export default function AdminPanel({ onBack }: Props) {
  const [overview, setOverview] = useState<AdminOverview | null>(null)
  const [trainers, setTrainers] = useState<AdminTrainer[] | null>(null)
  const [invites, setInvites] = useState<{ created_at: string; expires_at: string }[]>([])
  const [opened, setOpened] = useState<AdminTrainer | null>(null)
  const [invite, setInvite] = useState<{ url: string; expires_at: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reloads, setReloads] = useState(0)
  const [promo, setPromo] = useState(false)

  useEffect(() => {
    Promise.all([fetchAdminOverview(), fetchAdminTrainers(), fetchOpenInvites()])
      .then(([data, list, open]) => {
        setOverview(data)
        setTrainers(list)
        setInvites(open)
      })
      .catch((err: unknown) => setError(errorText(err)))
  }, [reloads])

  async function newInvite() {
    try {
      const created = await createTrainerInvite()
      haptic.success()
      setInvite(created)
      setReloads((count) => count + 1)
    } catch (err) {
      haptic.error()
      setError(errorText(err))
    }
  }

  return (
    <Screen title="Админ-панель" subtitle="Цифры по всей платформе" onBack={onBack}>
      {error && <ErrorText>{error}</ErrorText>}
      {(overview === null || trainers === null) && !error && <SkeletonList rows={4} />}
      {overview && trainers && (
        <>
          <div className="stat-grid">
            <Tile
              wide
              label="Пользуются Trenio"
              value={`${overview.trainers_engaged} из ${overview.trainers_active}`}
              note="тренеров заходили хотя бы 10 из последних 14 дней"
            />
            <Tile
              label="Тренеры"
              value={String(overview.trainers)}
              note={`активны: ${overview.trainers_active}`}
            />
            <Tile
              label="Клиенты"
              value={String(overview.clients)}
              note={`+${overview.clients_new_week} за неделю`}
            />
            <Tile
              label="Пользователи"
              value={String(overview.users)}
              note={`сегодня ${overview.users_active_today}, за 7 дн ${overview.users_seen_week}`}
            />
            <Tile
              label="Записи за 7 дн"
              value={String(overview.bookings_week)}
              note={`прошло ${overview.attended_week}, впереди ${overview.upcoming_week}`}
            />
          </div>
          <Section
            title="Деньги платформы за месяц"
            footer="Общие суммы по всем тренерам, без разбивки по каждому. Разовые занятия — по цене услуги."
          >
            <Row title="Получено" value={rubles(overview.money.received)} />
            <Row title="Прошлый месяц" value={rubles(overview.money.received_prev)} />
            <Row
              title="Продано блоков"
              value={`${overview.money.packages_sold} на ${rubles(overview.money.packages_amount)}`}
            />
          </Section>
          <Section title="Новые по неделям">
            <WeeksChart weeks={overview.weeks} />
          </Section>
          <Section
            title="Воронка тренеров"
            footer="Настроили — есть услуга и рабочие часы. Записи — за последние 7 дней."
          >
            <Funnel
              steps={[
                ['Действующие тренеры', overview.funnel.trainers],
                ['Заполнили профиль', overview.funnel.onboarded],
                ['Настроили услуги и часы', overview.funnel.set_up],
                ['Есть клиенты', overview.funnel.with_clients],
                ['Есть записи', overview.funnel.with_bookings],
              ]}
            />
          </Section>
          <Section title={`Тренеры · ${trainers.length}`}>
            {trainers.map((trainer) => {
              const [label, tone] = STATE[trainer.state]
              return (
                <Row
                  key={trainer.id}
                  leading={<TrainerAvatar trainer={trainer} />}
                  title={trainer.display_name}
                  subtitle={`${plural(trainer.clients, 'клиент', 'клиента', 'клиентов')} · заходил ${activeCount(trainer)} из 14 дн · ${ago(trainer.last_seen_at)}`}
                  badge={<span className={`badge ${tone}`}>{label}</span>}
                  onClick={() => setOpened(trainer)}
                />
              )
            })}
          </Section>
          <Section
            title="Приглашения"
            footer={`Ссылка одноразовая: по ней один человек получает доступ тренера.${invites.length > 0 ? ` Не использовано: ${invites.length}.` : ''}`}
          >
            {invite && (
              <Row
                title="Отправить приглашение"
                subtitle={`до ${dateTime(invite.expires_at, TIMEZONE)}`}
                icon={{ name: 'share', color: 'var(--c-accent)' }}
                onClick={() => {
                  haptic.tap()
                  shareLink(invite.url, 'Приглашение в Trenio для тренера')
                }}
              />
            )}
            {invites
              .filter((item) => item.expires_at !== invite?.expires_at)
              .map((item) => (
                <Row
                  key={item.expires_at}
                  title="Неиспользованная ссылка"
                  subtitle={`создана ${shortDate(item.created_at.slice(0, 10))}, действует до ${shortDate(item.expires_at.slice(0, 10))}`}
                  tone="muted"
                />
              ))}
            <AddRow title="Создать приглашение" onClick={() => void newInvite()} />
          </Section>
          <Section>
            <Row
              title="Промо от автора"
              subtitle="Карточка с промокодом у тренеров и клиентов"
              icon={{ name: 'ticket', color: 'var(--c-violet)' }}
              chevron
              onClick={() => setPromo(true)}
            />
          </Section>
          <Section title="Сервер">
            <Row title="Версия" value={overview.version} />
            <Row
              title="Уведомления за сутки"
              subtitle={`ушло ${overview.notifications_sent_day}, не дошло ${overview.notifications_failed_day}`}
            />
          </Section>
        </>
      )}
      {promo && <AdminPromo onBack={() => setPromo(false)} />}
      {opened && (
        <TrainerScreen
          trainer={opened}
          onBack={() => setOpened(null)}
          onChanged={() => {
            setOpened(null)
            setReloads((count) => count + 1)
          }}
        />
      )}
    </Screen>
  )
}

function activeCount(trainer: AdminTrainer): number {
  return trainer.active_days.filter(Boolean).length
}

type TileProps = { label: string; value: string; note?: string; wide?: boolean }

function Tile({ label, value, note, wide = false }: TileProps) {
  return (
    <div className={wide ? 'stat-tile wide' : 'stat-tile'}>
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      {note && <span className="stat-note">{note}</span>}
    </div>
  )
}

function WeeksChart({ weeks }: { weeks: AdminOverview['weeks'] }) {
  const max = Math.max(1, ...weeks.flatMap((w) => [w.new_clients, w.new_trainers]))
  const height = (count: number) => `${Math.round((count / max) * 100)}%`
  return (
    <div className="group bar-chart-card">
      <div className="bar-chart" role="list">
        {weeks.map((week) => (
          <div
            key={week.start}
            role="listitem"
            className="bar-month"
            aria-label={`Неделя с ${longDate(week.start)}: клиентов ${week.new_clients}, тренеров ${week.new_trainers}`}
          >
            <span className="bar-pair">
              <span className="bar received" style={{ height: height(week.new_clients) }} />
              <span className="bar planned" style={{ height: height(week.new_trainers) }} />
            </span>
            <span className="bar-label">{dayOfMonth(week.start)}</span>
          </div>
        ))}
      </div>
      <div className="bar-legend">
        <span>
          <i className="received" />
          клиенты
        </span>
        <span>
          <i className="planned" />
          тренеры
        </span>
        <span className="bar-max">недели с понедельника</span>
      </div>
    </div>
  )
}

function Funnel({ steps }: { steps: [string, number][] }) {
  const top = Math.max(1, steps[0][1])
  return (
    <>
      {steps.map(([label, count]) => (
        <Row
          key={label}
          title={
            <span className="funnel-step">
              <span>{label}</span>
              <b>{count}</b>
              <span className="funnel-bar">
                <i style={{ width: `${Math.round((count / top) * 100)}%` }} />
              </span>
            </span>
          }
        />
      ))}
    </>
  )
}

type TrainerScreenProps = {
  trainer: AdminTrainer
  onBack: () => void
  onChanged: () => void
}

function TrainerScreen({ trainer, onBack, onChanged }: TrainerScreenProps) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const disabled = trainer.state === 'disabled'
  const username = trainer.user.username

  async function toggle() {
    const ok = disabled
      ? true
      : await confirmAction(
          `Отключить доступ тренера «${trainer.display_name}»? Данные сохранятся, доступ можно вернуть.`,
          'Отключить',
        )
    if (!ok) return
    setBusy(true)
    try {
      await setTrainerActive(trainer.id, disabled)
      haptic.success()
      onChanged()
    } catch (err) {
      haptic.error()
      setError(errorText(err))
      setBusy(false)
    }
  }

  return (
    <Screen
      title={trainer.display_name}
      subtitle={`${username ? `@${username} · ` : ''}тренер с ${longDate(trainer.since.slice(0, 10))}`}
      avatar={<TrainerAvatar trainer={trainer} size="md" />}
      onBack={onBack}
    >
      <div className="stat-grid">
        <Tile
          label="Клиенты"
          value={String(trainer.clients)}
          note={`+${trainer.clients_new_week} за неделю`}
        />
        <Tile
          label="Записи за 30 дн"
          value={String(trainer.bookings_month)}
          note={`прошло ${trainer.attended_month}`}
        />
        <Tile label="Услуги" value={String(trainer.services)} />
        <Tile label="Статус" value={STATE[trainer.state][0]} />
      </div>
      <Section
        title="Активность за 14 дней"
        footer="Каждая клетка — день, справа сегодня. Закрашена, если тренер открывал приложение."
      >
        <div className="activity-strip" aria-label={`Заходил ${activeCount(trainer)} из 14 дней`}>
          {trainer.active_days.map((active, index) => (
            <i key={index} className={active ? 'on' : undefined} />
          ))}
        </div>
        <Row title="Дней подряд" value={String(trainer.streak)} />
        <Row title="Поставил записей сам" value={String(trainer.bookings_created)} />
        <Row title="Отметил занятий" value={String(trainer.marks)} />
      </Section>
      <Section>
        <Row title="Заходил в приложение" value={ago(trainer.last_seen_at)} />
        <Row
          title="Последнее занятие"
          subtitle={trainer.last_booking_at ? dateTime(trainer.last_booking_at, TIMEZONE) : 'нет'}
        />
        <Row title="Часовой пояс" value={trainer.timezone} />
      </Section>
      {error && <ErrorText>{error}</ErrorText>}
      <Section>
        {username && (
          <Row
            title="Написать в Telegram"
            tone="accent"
            centered
            onClick={() => openTelegram(`https://t.me/${username}`)}
          />
        )}
        {!trainer.is_admin && (
          <Row
            title={disabled ? 'Вернуть доступ' : 'Отключить доступ'}
            tone={disabled ? 'accent' : 'destructive'}
            centered
            onClick={busy ? undefined : () => void toggle()}
          />
        )}
      </Section>
    </Screen>
  )
}
