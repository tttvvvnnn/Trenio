import { useState } from 'react'
import type { AdminTrainer, FeedKind, Insights, Money, Overview } from '../api'
import { monthName, plural, rub, shortDate, time, tint, today } from '../format'
import { useData } from '../useData'
import {
  Avatar,
  Bars,
  ErrorTile,
  Line,
  Skeleton,
  type ScreenProps,
} from './common'
import { FEED_COLOR, FEED_LABEL, STATE_COLOR, STATE_LABEL } from './labels'

const FILTERS: { label: string; kinds: FeedKind[] | null }[] = [
  { label: 'Всё', kinds: null },
  { label: 'Тренеры', kinds: ['joined', 'quiet'] },
  { label: 'Клиенты', kinds: ['first_client', 'first_client_booking', 'first_package'] },
  { label: 'Сбои', kinds: ['error'] },
]

export default function Summary({ onUnauthorized }: ScreenProps) {
  const overview = useData<Overview>('/admin/overview', onUnauthorized)
  const insights = useData<Insights>('/admin/insights', onUnauthorized)
  const trainers = useData<AdminTrainer[]>('/admin/trainers', onUnauthorized)
  const money = useData<Money>('/admin/money', onUnauthorized)
  const [filter, setFilter] = useState(0)

  const failed = overview.error ?? insights.error ?? trainers.error ?? money.error
  if (failed) {
    return (
      <ErrorTile
        text={failed}
        onRetry={() => [overview, insights, trainers, money].forEach((item) => item.reload())}
      />
    )
  }
  if (!overview.data || !insights.data || !trainers.data || !money.data) {
    return (
      <>
        <Skeleton span="span-8" />
        <Skeleton span="span-4" />
        <Skeleton span="span-7" />
        <Skeleton span="span-5" />
      </>
    )
  }
  const o = overview.data
  const ins = insights.data
  const list = trainers.data
  const m = money.data
  const seenToday = list.filter((t) => t.active_days[t.active_days.length - 1]).length
  const kinds = FILTERS[filter].kinds
  const feed = ins.feed.filter((event) => !kinds || kinds.includes(event.kind)).slice(0, 8)
  // Когорты идут от старой к новой: берём самую свежую, по которой уже есть результат
  const cohortsNewFirst = [...ins.cohorts].reverse()
  const latestCohort = cohortsNewFirst.find((c) => c.alive.some((v) => v !== null) && c.trainers > 0)
  const retentionIndex = latestCohort ? latestCohort.alive.findLastIndex((v) => v !== null) : -1
  const retained = latestCohort && retentionIndex >= 0 ? (latestCohort.alive[retentionIndex] ?? 0) : null
  const retention = latestCohort && retained !== null ? Math.round((100 * retained) / latestCohort.trainers) : null

  return (
    <>
      <section className="glass tile span-8" aria-labelledby="s-today" style={{ padding: 28, gap: 22 }}>
        <div className="tile-head">
          <h1 id="s-today">Сегодня в Trenio</h1>
          <span className="muted small">{today()}</span>
        </div>
        <div className="kpis">
          <Kpi label="Тренеры заходили" value={`${seenToday} из ${o.trainers_active}`} sub={`за 2 недели регулярно: ${o.trainers_engaged}`} />
          <Kpi label="Занятий за неделю" value={o.attended_week} sub={`впереди на неделе: ${o.upcoming_week}`} />
          <Kpi label="Новые клиенты" value={o.clients_new_week} sub={`всего клиентов: ${o.clients}`} />
          <Kpi label="Записей за неделю" value={o.bookings_week} sub={`клиенты сами: ${ins.pulse.self_booked.at(-1) ?? 0}%`} />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <span className="muted small">Прошедшие занятия по неделям</span>
          <Bars values={ins.pulse.sessions} height={72} label={`Занятия по неделям: ${ins.pulse.sessions.join(', ')}`} />
          <div className="tiny muted" style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>{ins.pulse.sessions.length} недель назад</span>
            <span>эта неделя</span>
          </div>
        </div>
      </section>

      <section className="tile accent span-4 stretch" aria-labelledby="s-mrr" style={{ padding: 28 }}>
        <div className="tile-head">
          <h2 id="s-mrr" style={{ fontSize: 15, fontWeight: 500 }} className="muted">
            MRR
          </h2>
          <a href="#/money" className="small">
            Деньги →
          </a>
        </div>
        <span className="huge num">{rub(m.mrr)}</span>
        <span className="small muted">
          платящих {m.paying}, на пробном периоде {m.trials}
        </span>
        <div style={{ marginTop: 'auto' }}>
          <Line
            values={[...m.months.map((x) => x.received), m.forecast.realistic]}
            dashed={1}
            color="#ffffff"
            label={`Получено по месяцам: ${m.months.map((x) => x.received).join(', ')}; прогноз ${m.forecast.realistic}`}
          />
          <div className="tiny muted num" style={{ display: 'flex', justifyContent: 'space-between' }}>
            {m.months.map((x) => (
              <span key={x.month}>{monthName(x.month)}</span>
            ))}
            <span>прогноз</span>
          </div>
        </div>
        <div className="small" style={{ borderTop: '1px solid rgba(255,255,255,.25)', paddingTop: 12 }}>
          Через месяц, скорее всего, <b className="num">{rub(m.forecast.realistic)}</b>. Если продлят все:{' '}
          {rub(m.forecast.optimistic)}.
        </div>
      </section>

      <section className="glass tile span-7" aria-labelledby="s-feed">
        <div className="tile-head" style={{ alignItems: 'center' }}>
          <h2 id="s-feed">Что происходит</h2>
          <div className="glass segmented" role="group" aria-label="Фильтр ленты" style={{ boxShadow: 'none' }}>
            {FILTERS.map((item, index) => (
              <button key={item.label} type="button" aria-pressed={index === filter} onClick={() => setFilter(index)}>
                {item.label}
              </button>
            ))}
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {feed.length === 0 && <p className="muted">За последние 30 дней событий нет.</p>}
          {feed.map((event, index) => (
            <div className="feed-item" key={`${event.at}-${index}`}>
              <span className="feed-icon" aria-hidden="true" style={{ background: tint(FEED_COLOR[event.kind]) }}>
                <span className="dot" style={{ width: 10, height: 10, background: FEED_COLOR[event.kind] }} />
              </span>
              <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                <span>{event.text}</span>
                <span className="tiny muted">{FEED_LABEL[event.kind]}</span>
              </div>
              <span className="small muted num">
                {shortDate(event.at)} {time(event.at)}
              </span>
            </div>
          ))}
        </div>
      </section>

      <section className="glass tile span-5" aria-labelledby="s-ret">
        <h2 id="s-ret">Тренеры остаются?</h2>
        {latestCohort && retention !== null ? (
          <div style={{ display: 'flex', gap: 18, alignItems: 'center' }}>
            <Ring percent={retention} />
            <p className="muted" style={{ margin: 0 }}>
              Из <b style={{ color: 'var(--text)' }}>{latestCohort.trainers}</b> тренеров, пришедших на неделе с{' '}
              {shortDate(latestCohort.start)}, через {ins.cohort_points[retentionIndex]} нед. всё ещё ведут
              занятия <b style={{ color: 'var(--text)' }}>{retained}</b>. Чем выше процент, тем нужнее Trenio.
            </p>
          </div>
        ) : (
          <p className="muted" style={{ margin: 0 }}>
            Пока мало данных: удержание появится через неделю после прихода первых тренеров.
          </p>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {cohortsNewFirst.slice(0, 4).map((cohort) => {
            const alive = cohort.alive.filter((v): v is number => v !== null).at(-1)
            const percent = alive === undefined || !cohort.trainers ? null : Math.round((100 * alive) / cohort.trainers)
            return (
              <div key={cohort.start} className="small" style={{ display: 'grid', gridTemplateColumns: '90px minmax(0,1fr) 44px', gap: 10, alignItems: 'center' }}>
                <span className="muted">с {shortDate(cohort.start)}</span>
                <span style={{ height: 10, borderRadius: 5, background: 'var(--well)', overflow: 'hidden' }}>
                  <span style={{ display: 'block', height: '100%', width: `${percent ?? 0}%`, background: 'var(--coral)', borderRadius: 5 }} />
                </span>
                <span className="num" style={{ textAlign: 'right' }}>
                  {percent === null ? '—' : `${percent}%`}
                </span>
              </div>
            )
          })}
        </div>
      </section>

      <section className="glass tile span-7" aria-labelledby="s-tr" style={{ gap: 6 }}>
        <div className="tile-head" style={{ paddingBottom: 6 }}>
          <h2 id="s-tr">Тренеры за 7 дней</h2>
          <a href="#/trainers" className="small">
            Все тренеры
          </a>
        </div>
        {list.slice(0, 6).map((trainer) => {
          const week = trainer.active_days.slice(-7)
          return (
            <div key={trainer.id} className="row" style={{ gridTemplateColumns: 'minmax(0,1.3fr) minmax(0,1fr) 120px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
                <Avatar id={trainer.id} name={trainer.display_name} url={trainer.avatar_url} size={36} />
                <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                  <span style={{ fontWeight: 500 }}>{trainer.display_name}</span>
                  <span className="tiny" style={{ color: STATE_COLOR[trainer.state] }}>
                    {trainer.is_admin ? 'админ' : STATE_LABEL[trainer.state]}
                  </span>
                </div>
              </div>
              <Bars
                values={week.map((day) => (day ? 1 : 0))}
                height={24}
                gap={4}
                label={`Заходил ${week.filter(Boolean).length} из 7 дней`}
              />
              <span className="num" style={{ textAlign: 'right' }}>
                <b>{trainer.bookings_created}</b>{' '}
                <span className="tiny muted">
                  {plural(trainer.bookings_created, 'запись', 'записи', 'записей')} за 2 нед.
                </span>
              </span>
            </div>
          )
        })}
      </section>

      <section className="glass tile span-5" aria-labelledby="s-sys">
        <div className="tile-head" style={{ alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span
              className="dot"
              aria-hidden="true"
              style={{ width: 10, height: 10, background: ins.health.errors_day ? 'var(--amber)' : '#22A35A' }}
            />
            <h2 id="s-sys">{ins.health.errors_day ? 'Есть ошибки' : 'Приложение работает'}</h2>
          </div>
          <a href="#/system" className="small">
            Система
          </a>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0,1fr))', gap: 10 }}>
          <Kpi label="Версия" value={ins.health.version} small />
          <Kpi
            label="Уведомления, 24 ч"
            value={`${ins.health.notifications_sent_day} · сбоев ${ins.health.notifications_failed_day}`}
            small
          />
          <Kpi label="Ошибки Mini App, 24 ч" value={ins.health.errors_day} small />
          <Kpi label="Открытые приглашения" value={o.invites_open} small />
        </div>
        {ins.attention.length > 0 && (
          <a href="#/trainers" className="notice" style={{ color: 'var(--text)', textDecoration: 'none', background: tint('var(--red)') }}>
            Требуют внимания: {ins.attention.length} {ins.attention.length === 1 ? 'тренер' : 'тренера'} →
          </a>
        )}
      </section>
    </>
  )
}

function Kpi({ label, value, sub, small }: { label: string; value: string | number; sub?: string; small?: boolean }) {
  return (
    <div className="well">
      <span className="small muted">{label}</span>
      <span className={small ? 'num' : 'big num'} style={small ? { fontWeight: 600 } : undefined}>
        {value}
      </span>
      {sub && <span className="small muted">{sub}</span>}
    </div>
  )
}

function Ring({ percent }: { percent: number }) {
  const length = 2 * Math.PI * 32
  return (
    <svg role="img" aria-label={`${percent} процентов`} viewBox="0 0 80 80" width="104" height="104" style={{ flex: '0 0 auto' }}>
      <circle cx="40" cy="40" r="32" fill="none" stroke="var(--well)" strokeWidth="10" />
      <circle
        cx="40"
        cy="40"
        r="32"
        fill="none"
        stroke="var(--coral)"
        strokeWidth="10"
        strokeLinecap="round"
        strokeDasharray={`${(length * percent) / 100} ${length}`}
        transform="rotate(-90 40 40)"
      />
      <text x="40" y="45" textAnchor="middle" fontSize="17" fontWeight="600" fill="var(--text)">
        {percent}%
      </text>
    </svg>
  )
}
