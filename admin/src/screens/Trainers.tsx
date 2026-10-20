import { useEffect, useState } from 'react'
import { post, type AdminTrainer, type Insights, type NewInvite, type OpenInvite, type Overview } from '../api'
import { ago, shortDate, tint } from '../format'
import { useData } from '../useData'
import {
  Avatar,
  Bars,
  ErrorTile,
  PageTitle,
  Skeleton,
  type ScreenProps,
} from './common'
import { ATTENTION_TEXT, STATE_COLOR, STATE_LABEL } from './labels'
import { TrainerActionDialog, type TrainerAction } from './TrainerActions'

type Filter = 'all' | 'active' | 'attention' | 'disabled'

const FILTERS: { id: Filter; label: string; match: (t: AdminTrainer) => boolean }[] = [
  { id: 'all', label: 'Все', match: () => true },
  { id: 'active', label: 'Работают', match: (t) => t.state === 'active' },
  { id: 'attention', label: 'Требуют внимания', match: (t) => t.state === 'quiet' || t.state === 'not_set_up' },
  { id: 'disabled', label: 'Отключены', match: (t) => t.state === 'disabled' },
]

function planText(trainer: AdminTrainer): string {
  const now = new Date()
  if (trainer.pro_until && new Date(trainer.pro_until) > now) return `Pro до ${shortDate(trainer.pro_until)}`
  if (trainer.trial_until && new Date(trainer.trial_until) > now) return `пробный до ${shortDate(trainer.trial_until)}`
  return 'бесплатный'
}

const COLUMNS = 'minmax(0,1.6fr) 130px 80px minmax(0,1fr) 140px 52px'

export default function Trainers({ onUnauthorized }: ScreenProps) {
  const trainers = useData<AdminTrainer[]>('/admin/trainers', onUnauthorized)
  const overview = useData<Overview>('/admin/overview', onUnauthorized)
  const insights = useData<Insights>('/admin/insights', onUnauthorized)
  const invites = useData<OpenInvite[]>('/admin/invites', onUnauthorized)
  const [filter, setFilter] = useState<Filter>('all')
  const [query, setQuery] = useState('')
  const [menu, setMenu] = useState<number | null>(null)
  const [invite, setInvite] = useState<NewInvite | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [action, setAction] = useState<{ kind: TrainerAction; trainer: AdminTrainer } | null>(null)
  const [done, setDone] = useState<string | null>(null)

  // Меню закрывается по Esc и по клику мимо него
  useEffect(() => {
    if (menu === null) return
    const close = (event: Event) => {
      if (event instanceof KeyboardEvent ? event.key === 'Escape' : !(event.target as Element).closest('.menu, .icon-btn')) setMenu(null)
    }
    document.addEventListener('keydown', close)
    document.addEventListener('pointerdown', close)
    return () => {
      document.removeEventListener('keydown', close)
      document.removeEventListener('pointerdown', close)
    }
  }, [menu])

  const failed = trainers.error ?? overview.error ?? insights.error ?? invites.error
  if (failed) return <ErrorTile text={failed} onRetry={() => [trainers, overview, insights, invites].forEach((x) => x.reload())} />
  if (!trainers.data || !overview.data || !insights.data || !invites.data) {
    return (
      <>
        <Skeleton span="span-12" />
        <Skeleton span="span-6" />
        <Skeleton span="span-6" />
      </>
    )
  }
  const list = trainers.data
  const byId = new Map(list.map((t) => [t.id, t]))
  const needle = query.trim().toLowerCase()
  const rows = list
    .filter(FILTERS.find((f) => f.id === filter)!.match)
    .filter(
      (t) =>
        !needle ||
        t.display_name.toLowerCase().includes(needle) ||
        (t.user.username ?? '').toLowerCase().includes(needle) ||
        String(t.id) === needle,
    )
  const funnel = overview.data.funnel

  const toggle = async (trainer: AdminTrainer) => {
    const enable = trainer.state === 'disabled'
    const question = enable
      ? `Вернуть доступ тренеру ${trainer.display_name}?`
      : `Отключить ${trainer.display_name}? Тренер и его клиенты не смогут пользоваться Trenio, данные сохранятся.`
    if (!window.confirm(question)) return
    setBusy(true)
    setError(null)
    try {
      await post(`/admin/trainers/${trainer.id}/active`, { active: enable })
      setMenu(null)
      trainers.reload()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не получилось')
    } finally {
      setBusy(false)
    }
  }

  const newInvite = async () => {
    setBusy(true)
    setError(null)
    try {
      setInvite(await post<NewInvite>('/admin/invites'))
      invites.reload()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не получилось')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <PageTitle sub={`${list.length} тренеров · бот основной`} title="Тренеры">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
          <label className="glass" style={{ display: 'flex', alignItems: 'center', gap: 8, minHeight: 44, padding: '0 14px', borderRadius: 14, width: 280 }}>
            <span className="sr">Поиск тренера</span>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Имя, @username или номер"
              style={{ flex: 1, minWidth: 0, border: 0, background: 'transparent', font: 'inherit', fontSize: 14, color: 'var(--text)', outline: 'none' }}
            />
          </label>
          <div className="chips" role="group" aria-label="Фильтр">
            {FILTERS.map((item) => (
              <button key={item.id} type="button" className="chip" aria-pressed={item.id === filter} onClick={() => setFilter(item.id)}>
                {item.label} <span className="num muted">{list.filter(item.match).length}</span>
              </button>
            ))}
          </div>
        </div>
      </PageTitle>

      {error && (
        <p className="notice span-12" role="alert" style={{ color: 'var(--red)', margin: 0 }}>
          {error}
        </p>
      )}
      {done && (
        <p className="notice span-12" role="status" style={{ color: 'var(--green)', margin: 0 }}>
          {done}
        </p>
      )}
      {action && (
        <TrainerActionDialog
          action={action.kind}
          trainer={action.trainer}
          onClose={() => setAction(null)}
          onDone={(note) => {
            setAction(null)
            setDone(note)
            trainers.reload()
          }}
        />
      )}

      {/* С открытым меню список выше соседних плиток: у стекла свой слой (backdrop-filter), и меню иначе уходит под следующую */}
      <section
        className="glass tile span-12"
        aria-label="Список тренеров"
        style={{ padding: '12px 16px 16px', gap: 0, position: 'relative', zIndex: menu === null ? undefined : 5 }}
      >
        <div className="tiny muted" style={{ display: 'grid', gridTemplateColumns: COLUMNS, gap: 14, padding: '10px 12px' }}>
          <span>Тренер</span>
          <span>Состояние</span>
          <span style={{ textAlign: 'right' }}>Клиенты</span>
          <span>Заходил за 14 дней</span>
          <span>Последний вход</span>
          <span />
        </div>
        {rows.length === 0 && <p className="muted" style={{ padding: 12 }}>Никого не нашлось.</p>}
        {rows.map((trainer) => (
          <div
            key={trainer.id}
            style={{
              position: 'relative',
              display: 'grid',
              gridTemplateColumns: COLUMNS,
              gap: 14,
              alignItems: 'center',
              minHeight: 64,
              padding: '0 12px',
              borderRadius: 18,
              background: menu === trainer.id ? 'var(--well)' : 'transparent',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
              <Avatar id={trainer.id} name={trainer.display_name} url={trainer.avatar_url} size={40} />
              <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                <span style={{ fontWeight: 500 }}>{trainer.display_name}</span>
                <span className="tiny muted">
                  {trainer.user.username ? `@${trainer.user.username} · ` : ''}№ {trainer.id} · с {shortDate(trainer.since)}
                </span>
              </div>
            </div>
            <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 3 }}>
              <span className="badge" style={{ background: tint(STATE_COLOR[trainer.state]), color: STATE_COLOR[trainer.state] }}>
                {trainer.is_admin ? 'админ' : STATE_LABEL[trainer.state]}
              </span>
              {!trainer.is_admin && <span className="tiny muted">{planText(trainer)}</span>}
            </span>
            <span className="num" style={{ textAlign: 'right', fontWeight: 500 }}>
              {trainer.clients}
              {trainer.clients_new_week > 0 && <span className="tiny" style={{ color: 'var(--green)' }}> +{trainer.clients_new_week}</span>}
            </span>
            <Bars
              values={trainer.active_days.map((day) => (day ? 1 : 0))}
              height={26}
              gap={3}
              label={`Заходил ${trainer.active_days.filter(Boolean).length} из 14 дней, подряд ${trainer.streak}`}
            />
            <span className="small muted">{ago(trainer.last_seen_at)}</span>
            <button
              type="button"
              className="icon-btn"
              aria-label={`Действия: ${trainer.display_name}`}
              aria-expanded={menu === trainer.id}
              onClick={() => setMenu(menu === trainer.id ? null : trainer.id)}
            >
              <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                <circle cx="5" cy="12" r="2" />
                <circle cx="12" cy="12" r="2" />
                <circle cx="19" cy="12" r="2" />
              </svg>
            </button>
            {menu === trainer.id && (
              <div className="menu" role="menu">
                {trainer.user.username && (
                  <a role="menuitem" href={`https://t.me/${trainer.user.username}`} target="_blank" rel="noreferrer">
                    Написать в личку
                  </a>
                )}
                {[
                  ['message', 'Сообщение в бот'],
                  ...(trainer.is_admin ? [] : [['pro', 'Pro в подарок']]),
                ].map(([kind, label]) => (
                  <button
                    key={kind}
                    role="menuitem"
                    type="button"
                    onClick={() => {
                      setMenu(null)
                      setDone(null)
                      setAction({ kind: kind as TrainerAction, trainer })
                    }}
                  >
                    {label}
                  </button>
                ))}
                {!trainer.is_admin && (
                  <button
                    role="menuitem"
                    type="button"
                    disabled={busy}
                    onClick={() => toggle(trainer)}
                    style={{ color: trainer.state === 'disabled' ? 'var(--green)' : 'var(--amber)' }}
                  >
                    {trainer.state === 'disabled' ? 'Вернуть доступ' : 'Отключить'}
                  </button>
                )}
                {!trainer.is_admin && (
                  <button
                    role="menuitem"
                    type="button"
                    style={{ color: 'var(--red)' }}
                    onClick={() => {
                      setMenu(null)
                      setDone(null)
                      setAction({ kind: 'delete', trainer })
                    }}
                  >
                    Удалить…
                  </button>
                )}
              </div>
            )}
          </div>
        ))}
      </section>

      <section className="glass tile span-6" aria-labelledby="tr-path">
        <h2 id="tr-path">Путь тренера</h2>
        <p className="small muted" style={{ margin: 0 }}>
          Сколько действующих тренеров дошли до каждого шага.
        </p>
        {[
          ['Есть доступ', funnel.trainers],
          ['Прошли настройку', funnel.onboarded],
          ['Есть услуга и часы', funnel.set_up],
          ['Есть клиенты', funnel.with_clients],
          ['Записи за 7 дней', funnel.with_bookings],
        ].map(([label, value]) => (
          <div key={label} style={{ display: 'grid', gridTemplateColumns: '170px minmax(0,1fr) 40px', gap: 12, alignItems: 'center' }}>
            <span>{label}</span>
            <span style={{ height: 28, borderRadius: 10, background: 'var(--well)', overflow: 'hidden' }}>
              <span
                style={{
                  display: 'block',
                  height: '100%',
                  width: `${funnel.trainers ? (100 * Number(value)) / funnel.trainers : 0}%`,
                  background: 'linear-gradient(90deg, #FF8A66, #FF5A36)',
                  borderRadius: 10,
                }}
              />
            </span>
            <span className="num" style={{ textAlign: 'right', fontWeight: 600 }}>
              {value}
            </span>
          </div>
        ))}
      </section>

      <section className="glass tile span-6" aria-labelledby="tr-att">
        <h2 id="tr-att">Требуют внимания</h2>
        {insights.data.attention.length === 0 && <p className="muted" style={{ margin: 0 }}>Все в порядке.</p>}
        {insights.data.attention.map((item) => {
          const trainer = byId.get(item.trainer_id)
          return (
            <div key={`${item.trainer_id}-${item.reason}`} className="well" style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
              <span className="dot" aria-hidden="true" style={{ background: item.reason === 'quiet' ? 'var(--red)' : 'var(--amber)' }} />
              <span>
                <b style={{ fontWeight: 600 }}>{trainer?.display_name ?? `№ ${item.trainer_id}`}</b>{' '}
                {(ATTENTION_TEXT[item.reason] ?? ((n: number) => `${item.reason} (${n})`))(item.count)}
              </span>
              {trainer?.user.username && (
                <a className="btn secondary small" style={{ marginLeft: 'auto', whiteSpace: 'nowrap' }} href={`https://t.me/${trainer.user.username}`} target="_blank" rel="noreferrer">
                  Написать
                </a>
              )}
            </div>
          )
        })}
      </section>

      <section className="glass tile span-12" aria-labelledby="tr-inv">
        <div className="tile-head" style={{ alignItems: 'center' }}>
          <div>
            <h2 id="tr-inv">Приглашения</h2>
            <span className="small muted">Одноразовая ссылка для нового тренера. Открытых сейчас: {invites.data.length}</span>
          </div>
          <button type="button" className="btn" disabled={busy} onClick={newInvite}>
            Новая ссылка
          </button>
        </div>
        {invite && (
          <div className="notice" style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center' }}>
            <code style={{ wordBreak: 'break-all' }}>{invite.url}</code>
            <span className="small muted">действует до {shortDate(invite.expires_at)}</span>
            <button type="button" className="btn secondary small" onClick={() => navigator.clipboard?.writeText(invite.url)}>
              Скопировать
            </button>
          </div>
        )}
      </section>
    </>
  )
}
