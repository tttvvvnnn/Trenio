import { useState } from 'react'
import { post, type ActiveSession, type AuditEntry, type Insights, type Overview } from '../api'
import { ago, shortDate, time } from '../format'
import { useData } from '../useData'
import { ErrorTile, PageTitle, Skeleton, type ScreenProps } from './common'
import { auditText } from './labels'

export default function System({ onUnauthorized }: ScreenProps) {
  const insights = useData<Insights>('/admin/insights', onUnauthorized)
  const overview = useData<Overview>('/admin/overview', onUnauthorized)
  const sessions = useData<ActiveSession[]>('/admin/auth/sessions', onUnauthorized)
  const audit = useData<AuditEntry[]>('/admin/audit', onUnauthorized)
  const [error, setError] = useState<string | null>(null)

  const failed = insights.error ?? overview.error ?? sessions.error
  if (failed) return <ErrorTile text={failed} onRetry={() => [insights, overview, sessions].forEach((x) => x.reload())} />
  if (!insights.data || !overview.data || !sessions.data) return <Skeleton span="span-12" />
  const h = insights.data.health
  const o = overview.data
  const sent = o.notifications_sent_day
  const failedCount = o.notifications_failed_day
  const errors = insights.data.feed.filter((event) => event.kind === 'error')

  const revoke = async (id: string) => {
    if (!window.confirm('Завершить этот вход?')) return
    setError(null)
    try {
      await post(`/admin/auth/sessions/${id}/revoke`)
      sessions.reload()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не получилось')
    }
  }

  return (
    <>
      <PageTitle sub="состояние сервиса" title="Система" />

      <Status name="Backend" value={`v${h.version}`} sub="версия, которая сейчас работает" ok />
      <Status
        name="Уведомления, 24 ч"
        value={`${sent} отправлено`}
        sub={failedCount ? `${failedCount} не доставлено` : 'всё доставлено'}
        ok={failedCount === 0}
      />
      <Status
        name="Ошибки Mini App, 24 ч"
        value={String(h.errors_day)}
        sub={h.errors_day ? 'подробности в ленте ниже и в боте' : 'ошибок нет'}
        ok={h.errors_day === 0}
      />

      <section className="glass tile span-6" aria-labelledby="sy-err">
        <h2 id="sy-err">Ошибки за 30 дней</h2>
        {errors.length === 0 && <p className="muted" style={{ margin: 0 }}>Ошибок не было.</p>}
        {errors.slice(0, 8).map((event, index) => (
          <div key={`${event.at}-${index}`} className="well">
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
              <span style={{ fontWeight: 500 }}>{event.text}</span>
              <span className="small muted num">
                {shortDate(event.at)} {time(event.at)}
              </span>
            </div>
          </div>
        ))}
      </section>

      <section className="glass tile span-6" aria-labelledby="sy-ses">
        <h2 id="sy-ses">Входы в админку</h2>
        {error && (
          <p className="notice" role="alert" style={{ color: 'var(--red)', margin: 0 }}>
            {error}
          </p>
        )}
        {sessions.data.map((s) => (
          <div key={s.id} className="well" style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
            <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0, flex: 1 }}>
              <span style={{ fontWeight: 500 }}>
                {s.ip ?? 'адрес неизвестен'}
                {s.current && <span className="tiny" style={{ color: 'var(--green)' }}> · этот вход</span>}
              </span>
              <span className="tiny muted" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {s.user_agent ?? 'устройство неизвестно'}
              </span>
              <span className="tiny muted">
                вошли {shortDate(s.created_at)} {time(s.created_at)} · активность {ago(s.last_seen_at)}
              </span>
            </div>
            {!s.current && (
              <button type="button" className="btn danger small" onClick={() => revoke(s.id)}>
                Завершить
              </button>
            )}
          </div>
        ))}
      </section>

      <section className="glass tile span-12" aria-labelledby="sy-log">
        <div>
          <h2 id="sy-log">Журнал действий</h2>
          <span className="small muted">Входы и всё, что меняли в админке. Записи нельзя изменить или удалить.</span>
        </div>
        {audit.error && <p className="small muted">{audit.error}</p>}
        {audit.data?.length === 0 && <p className="muted" style={{ margin: 0 }}>Пока пусто.</p>}
        {audit.data?.map((entry) => (
          <div key={entry.id} style={{ display: 'grid', gridTemplateColumns: '110px minmax(0,1fr) 150px', gap: 12, alignItems: 'baseline', minHeight: 32 }}>
            <span className="small muted num">
              {shortDate(entry.created_at)} {time(entry.created_at)}
            </span>
            <span className="small" style={{ minWidth: 0, overflowWrap: 'anywhere' }}>
              {auditText(entry)}
            </span>
            <span className="tiny muted" style={{ textAlign: 'right' }}>
              {entry.web ? 'веб' : 'Mini App'}
              {entry.ip ? ` · ${entry.ip}` : ''}
            </span>
          </div>
        ))}
      </section>
    </>
  )
}

function Status({ name, value, sub, ok }: { name: string; value: string; sub: string; ok: boolean }) {
  const color = ok ? 'var(--green)' : 'var(--amber)'
  return (
    <section className="glass tile span-4" style={{ gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span className="dot" aria-hidden="true" style={{ width: 10, height: 10, background: color, boxShadow: `0 0 0 4px color-mix(in srgb, ${color} 20%, transparent)` }} />
        <span style={{ fontWeight: 500 }}>{name}</span>
      </div>
      <span className="num" style={{ fontSize: 26, fontWeight: 600 }}>
        {value}
      </span>
      <span className="small muted">{sub}</span>
    </section>
  )
}
