import { useEffect, useState } from 'react'

import {
  errorText,
  createTrainerInvite,
  fetchAdminInsights,
  fetchAdminOverview,
  fetchAdminTrainers,
  fetchOpenInvites,
  setTrainerActive,
  type AdminFeature,
  type AdminInsights,
  type AdminOverview,
  type AdminTrainer,
  type AdminTrainerState,
} from '../api'
import {
  dateTime,
  dayOfMonth,
  localDate,
  localTime,
  longDate,
  plural,
  rubles,
  shortDate,
} from '../format'
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

/** Админ-панель: растёт ли Trenio, кому из тренеров нужна помощь, что происходит. */
export default function AdminPanel({ onBack }: Props) {
  const [insights, setInsights] = useState<AdminInsights | null>(null)
  const [overview, setOverview] = useState<AdminOverview | null>(null)
  const [trainers, setTrainers] = useState<AdminTrainer[] | null>(null)
  const [invites, setInvites] = useState<{ created_at: string; expires_at: string }[]>([])
  const [opened, setOpened] = useState<AdminTrainer | null>(null)
  const [invite, setInvite] = useState<{ url: string; expires_at: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reloads, setReloads] = useState(0)
  const [promo, setPromo] = useState(false)
  const [allFeed, setAllFeed] = useState(false)
  const [allNumbers, setAllNumbers] = useState(false)

  useEffect(() => {
    Promise.all([
      fetchAdminInsights(),
      fetchAdminOverview(),
      fetchAdminTrainers(),
      fetchOpenInvites(),
    ])
      .then(([data, numbers, list, open]) => {
        setInsights(data)
        setOverview(numbers)
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

  const byId = new Map((trainers ?? []).map((trainer) => [trainer.id, trainer]))
  const reasons = new Map(
    (insights?.attention ?? []).map((item) => [item.trainer_id, reasonText(item)]),
  )

  function openTrainer(id: number | null) {
    const trainer = id === null ? undefined : byId.get(id)
    if (!trainer) return
    haptic.tap()
    setOpened(trainer)
  }

  return (
    <Screen title="Админ-панель" subtitle="Как идут дела у Trenio" onBack={onBack}>
      {error && <ErrorText>{error}</ErrorText>}
      {(insights === null || overview === null || trainers === null) && !error && (
        <SkeletonList rows={4} />
      )}
      {insights && overview && trainers && (
        <>
          <Pulse pulse={insights.pulse} />
          <Section
            title={`Требуют внимания · ${insights.attention.length}`}
            footer={
              insights.attention.length === 0
                ? 'Все тренеры настроились, работают и отмечают занятия.'
                : undefined
            }
          >
            {insights.attention.map((item) => {
              const trainer = byId.get(item.trainer_id)
              if (!trainer) return null
              const username = trainer.user.username
              return (
                <Row
                  key={item.trainer_id}
                  leading={<TrainerAvatar trainer={trainer} />}
                  title={trainer.display_name}
                  subtitle={reasonText(item)}
                  onClick={() => openTrainer(trainer.id)}
                  after={
                    username ? (
                      <button
                        type="button"
                        className="row-action"
                        onClick={() => openTelegram(`https://t.me/${username}`)}
                      >
                        Написать
                      </button>
                    ) : undefined
                  }
                />
              )
            })}
          </Section>
          <Section title="Лента" footer="События за 30 дней, новые сверху.">
            {insights.feed.length === 0 && <Row title="Пока ничего не происходило" tone="muted" />}
            {(allFeed ? insights.feed : insights.feed.slice(0, FEED_PREVIEW)).map((event) => (
              <Row
                key={`${event.kind}-${event.at}-${event.text}`}
                leading={<span className={`feed-dot ${event.kind}`} aria-hidden="true" />}
                title={event.text}
                value={when(event.at)}
                onClick={
                  event.trainer_id !== null && byId.has(event.trainer_id)
                    ? () => openTrainer(event.trainer_id)
                    : undefined
                }
              />
            ))}
            {!allFeed && insights.feed.length > FEED_PREVIEW && (
              <Row
                title={`Показать ещё ${insights.feed.length - FEED_PREVIEW}`}
                tone="accent"
                centered
                onClick={() => setAllFeed(true)}
              />
            )}
          </Section>
          <Section
            title="Удержание тренеров"
            footer="Сколько тренеров, пришедших на неделе, проводят занятия через 1, 2 и 4 недели. Админ не считается."
          >
            <Cohorts points={insights.cohort_points} cohorts={insights.cohorts} />
          </Section>
          <Section
            title="Чем пользуются"
            footer={`Из ${plural(insights.usage.base, 'тренера', 'тренеров', 'тренеров')} с занятиями за 30 дней.`}
          >
            <Bars
              steps={FEATURES.map(([key, label]) => [label, insights.usage.features[key]])}
              top={insights.usage.base}
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
          <Section title="Состояние">
            <Health health={insights.health} />
          </Section>
          <Section>
            <Row
              title="Промо от автора"
              subtitle="Карточка с промокодом у тренеров и клиентов"
              icon={{ name: 'ticket', color: 'var(--c-violet)' }}
              chevron
              onClick={() => setPromo(true)}
            />
            <Row
              title="Все цифры"
              subtitle="Пользователи, клиенты, деньги платформы, воронка"
              chevron={!allNumbers}
              onClick={() => setAllNumbers((open) => !open)}
            />
          </Section>
          {allNumbers && <AllNumbers overview={overview} />}
        </>
      )}
      {promo && <AdminPromo onBack={() => setPromo(false)} />}
      {opened && (
        <TrainerScreen
          trainer={opened}
          reason={reasons.get(opened.id)}
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

// Сколько событий ленты видно сразу
const FEED_PREVIEW = 8

const FEATURES: readonly (readonly [AdminFeature, string])[] = [
  ['self_booking', 'Клиенты записываются сами'],
  ['packages', 'Продают блоки'],
  ['reschedule', 'Переносят занятия'],
  ['notes', 'Пишут заметки к занятиям'],
  ['measurements', 'Ведут замеры'],
  ['rules', 'Завели правила'],
]

function reasonText({ reason, count }: AdminInsights['attention'][number]): string {
  const days = plural(count, 'день', 'дня', 'дней')
  switch (reason) {
    case 'not_set_up':
      return `не настроил услуги и часы, ${days}`
    case 'no_clients':
      return `нет клиентов, ${days}`
    case 'quiet':
      return `затих, ${days} без занятий`
    case 'unmarked':
      return `${plural(count, 'занятие', 'занятия', 'занятий')} без отметки`
  }
}

// Сегодня — время, вчера — «вчера», раньше — дата
function when(iso: string, now = new Date()): string {
  const day = localDate(iso, TIMEZONE)
  const today = localDate(now, TIMEZONE)
  if (day === today) return localTime(iso, TIMEZONE)
  const yesterday = localDate(new Date(now.getTime() - 86_400_000), TIMEZONE)
  if (day === yesterday) return 'вчера'
  return shortDate(day)
}

// «+3 к прошлой неделе», «как на прошлой»
function delta(current: number, previous: number, unit = ''): { text: string; tone: string } {
  const diff = current - previous
  if (diff === 0) return { text: 'как на прошлой неделе', tone: '' }
  const sign = diff > 0 ? '+' : '−'
  return {
    text: `${sign}${Math.abs(diff)}${unit} к прошлой неделе`,
    tone: diff > 0 ? 'success' : 'warning',
  }
}

function Pulse({ pulse }: { pulse: AdminInsights['pulse'] }) {
  const last = (values: number[]) => values[values.length - 1] ?? 0
  const prev = (values: number[]) => values[values.length - 2] ?? 0
  const live = delta(last(pulse.live_trainers), prev(pulse.live_trainers))
  const sessions = delta(last(pulse.sessions), prev(pulse.sessions))
  const share = pulse.self_booked[pulse.self_booked.length - 1]
  const sharePrev = pulse.self_booked[pulse.self_booked.length - 2]
  const shareDelta =
    share !== null && sharePrev !== null && share !== undefined && sharePrev !== undefined
      ? delta(share, sharePrev, ' п.п.')
      : null
  return (
    <div className="stat-grid">
      <div className="stat-tile wide pulse-tile">
        <div className="pulse-head">
          <span className="stat-label">Живые тренеры за неделю</span>
          <span className="stat-value pulse-value">{last(pulse.live_trainers)}</span>
          <span className={`stat-note ${live.tone}`}>{live.text}</span>
        </div>
        <Sparkline values={pulse.live_trainers} />
      </div>
      <Tile
        label="Занятий за неделю"
        value={String(last(pulse.sessions))}
        note={sessions.text}
        tone={sessions.tone}
      />
      <Tile
        label="Записались сами"
        value={share === null || share === undefined ? '—' : `${share}%`}
        note={shareDelta?.text ?? 'записей не было'}
        tone={shareDelta?.tone}
      />
      <p className="stat-hint">
        Живой тренер — у него за 7 дней прошло хотя бы одно занятие. «Записались сами» — доля новых
        записей, которые клиенты сделали без тренера.
      </p>
    </div>
  )
}

// Маленький график за 8 недель: последняя точка выделена
function Sparkline({ values }: { values: number[] }) {
  const width = 120
  const height = 44
  const max = Math.max(1, ...values)
  const step = values.length > 1 ? (width - 8) / (values.length - 1) : 0
  const points = values.map((value, index) => {
    const x = 4 + index * step
    const y = height - 4 - (value / max) * (height - 10)
    return [x, y] as const
  })
  const line = points.map(([x, y]) => `${x},${y}`).join(' ')
  const area = `4,${height - 4} ${line} ${4 + (values.length - 1) * step},${height - 4}`
  const [lastX, lastY] = points[points.length - 1] ?? [0, 0]
  return (
    <svg
      className="sparkline"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`По неделям: ${values.join(', ')}`}
    >
      <polygon points={area} className="sparkline-area" />
      <polyline points={line} className="sparkline-line" />
      <circle cx={lastX} cy={lastY} r={3} className="sparkline-dot" />
    </svg>
  )
}

function Cohorts({ points, cohorts }: { points: number[]; cohorts: AdminInsights['cohorts'] }) {
  return (
    <div className="group cohort-card">
      <table className="cohort-table">
        <thead>
          <tr>
            <th>Пришли</th>
            <th>тренеров</th>
            {points.map((weeks) => (
              <th key={weeks}>{weeks} нед</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {cohorts.map((cohort) => (
            <tr key={cohort.start}>
              <td>с {shortDate(cohort.start)}</td>
              <td>{cohort.trainers}</td>
              {cohort.alive.map((alive, index) => (
                <td key={index} className={alive === null ? 'muted' : undefined}>
                  {alive === null || cohort.trainers === 0 ? '—' : alive}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Health({ health }: { health: AdminInsights['health'] }) {
  const ok = health.errors_day === 0 && health.notifications_failed_day === 0
  return (
    <Row
      leading={<span className={`health-dot ${ok ? 'ok' : 'bad'}`} aria-hidden="true" />}
      title={ok ? 'Всё работает' : 'Есть сбои'}
      subtitle={`версия ${health.version} · ошибок в приложении за сутки ${health.errors_day} · уведомлений ушло ${health.notifications_sent_day}, не дошло ${health.notifications_failed_day}`}
    />
  )
}

// Прежние общие цифры: свёрнуты, открываются по нажатию
function AllNumbers({ overview }: { overview: AdminOverview }) {
  return (
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
        <Bars
          steps={[
            ['Действующие тренеры', overview.funnel.trainers],
            ['Заполнили профиль', overview.funnel.onboarded],
            ['Настроили услуги и часы', overview.funnel.set_up],
            ['Есть клиенты', overview.funnel.with_clients],
            ['Есть записи', overview.funnel.with_bookings],
          ]}
          top={overview.funnel.trainers}
        />
      </Section>
    </>
  )
}

function journey(trainer: AdminTrainer): [string, string | null][] {
  const steps = trainer.journey
  return [
    ['Стал тренером', trainer.since],
    ['Заполнил профиль', steps.onboarded_at],
    ['Первый клиент', steps.first_client_at],
    ['Клиент записался сам', steps.first_client_booking_at],
    ['Первый блок', steps.first_package_at],
  ]
}

function activeCount(trainer: AdminTrainer): number {
  return trainer.active_days.filter(Boolean).length
}

type TileProps = { label: string; value: string; note?: string; tone?: string; wide?: boolean }

function Tile({ label, value, note, tone, wide = false }: TileProps) {
  return (
    <div className={wide ? 'stat-tile wide' : 'stat-tile'}>
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      {note && <span className={tone ? `stat-note ${tone}` : 'stat-note'}>{note}</span>}
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

function Bars({ steps, top }: { steps: [string, number][]; top: number }) {
  const scale = Math.max(1, top)
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
                <i style={{ width: `${Math.round((count / scale) * 100)}%` }} />
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
  // Почему тренер в списке «Требуют внимания»
  reason?: string
  onBack: () => void
  onChanged: () => void
}

function TrainerScreen({ trainer, reason, onBack, onChanged }: TrainerScreenProps) {
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
      {reason && (
        <Section>
          <Row
            title="Требует внимания"
            subtitle={reason}
            icon={{ name: 'alert', color: 'var(--c-warning)' }}
          />
        </Section>
      )}
      <Section title="Путь в Trenio">
        {journey(trainer).map(([title, at]) => (
          <Row
            key={title}
            title={title}
            value={at ? longDate(localDate(at, TIMEZONE)) : 'ещё нет'}
            tone={at ? undefined : 'muted'}
          />
        ))}
      </Section>
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
