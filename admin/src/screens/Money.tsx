import type { Money as MoneyData, Risk } from '../api'
import { monthName, rub, shortDate, tint } from '../format'
import { useData } from '../useData'
import { ErrorTile, Line, PageTitle, Skeleton, type ScreenProps } from './common'

const RISK: Record<Risk, { label: string; color: string }> = {
  low: { label: 'надёжно', color: 'var(--green)' },
  medium: { label: 'средний риск', color: 'var(--amber)' },
  high: { label: 'высокий риск', color: 'var(--red)' },
}

export default function Money({ onUnauthorized }: ScreenProps) {
  const money = useData<MoneyData>('/admin/money', onUnauthorized)
  if (money.error) return <ErrorTile text={money.error} onRetry={money.reload} />
  if (!money.data) {
    return (
      <>
        <Skeleton span="span-8" />
        <Skeleton span="span-4" />
      </>
    )
  }
  const m = money.data
  const series = m.months.map((x) => x.received)
  const prev = series.at(-2) ?? 0
  const current = series.at(-1) ?? 0

  return (
    <>
      <PageTitle sub="подписки тренеров · все боты" title="Деньги" />

      <section className="glass tile span-8" aria-labelledby="m-mrr" style={{ padding: 28, gap: 18 }}>
        <div className="tile-head" style={{ alignItems: 'flex-end' }}>
          <div>
            <h2 id="m-mrr" className="muted" style={{ fontSize: 15, fontWeight: 500 }}>
              MRR, ежемесячная выручка от подписок
            </h2>
            <span className="num" style={{ fontSize: 56, fontWeight: 600, letterSpacing: '-0.03em' }}>
              {rub(m.mrr)}
            </span>
          </div>
          <span className="badge" style={{ fontSize: 14, padding: '6px 12px', background: tint('var(--green)'), color: 'var(--green)' }}>
            в этом месяце получено {rub(current)}
            {prev ? `, в прошлом ${rub(prev)}` : ''}
          </span>
        </div>
        <div style={{ color: 'var(--coral)' }}>
          <Line
            values={[...series, m.forecast.realistic]}
            dashed={1}
            color="var(--coral)"
            height={200}
            label={`Получено по месяцам: ${series.join(', ')}; прогноз ${m.forecast.realistic}`}
          />
        </div>
        <div className="tiny muted num" style={{ display: 'grid', gridTemplateColumns: `repeat(${series.length + 1}, minmax(0,1fr))`, marginTop: -8 }}>
          {m.months.map((x) => (
            <span key={x.month}>{monthName(x.month)}</span>
          ))}
          <span>прогноз</span>
        </div>
        <div className="kpis">
          <Stat label="Платящих тренеров" value={String(m.paying)} sub={`ещё ${m.trials} на пробном периоде`} />
          <Stat label="Средний чек" value={rub(m.arpu)} sub="в месяц" />
          <Stat
            label="Пробный → Pro"
            value={m.trial_conversion === null ? '—' : `${m.trial_conversion}%`}
            sub="из закончивших пробный период"
          />
          <Stat label="Всего получено" value={rub(m.received_total)} sub="деньгами, без баланса" />
        </div>
      </section>

      <section className="tile accent span-4 stretch" aria-labelledby="m-fc" style={{ padding: 28 }}>
        <h2 id="m-fc" className="muted" style={{ fontSize: 15, fontWeight: 500 }}>
          Прогноз MRR через месяц
        </h2>
        <span className="huge num">{rub(m.forecast.realistic)}</span>
        <span className="small muted">реалистичный сценарий</span>
        {[
          ['Оптимистично', m.forecast.optimistic, 'продлят все, пробные перейдут в Pro'],
          ['Реалистично', m.forecast.realistic, 'без тех, кто затих или отключён'],
          ['Осторожно', m.forecast.cautious, 'только надёжные продления Pro'],
        ].map(([label, sum, why], index) => (
          <div key={String(label)} style={{ padding: '12px 14px', borderRadius: 16, background: `rgba(255,255,255,${index === 1 ? 0.26 : 0.14})` }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ fontWeight: 500 }}>{label}</span>
              <b className="num">{rub(Number(sum))}</b>
            </div>
            <span className="tiny muted">{why}</span>
          </div>
        ))}
        <span className="tiny muted" style={{ marginTop: 'auto' }}>
          Считаем по датам окончания Pro и пробного периода и по тому, пользуется ли тренер Trenio.
        </span>
      </section>

      <section className="glass tile span-7" aria-labelledby="m-ren" style={{ gap: 6 }}>
        <h2 id="m-ren" style={{ paddingBottom: 8 }}>
          Ближайшие продления
        </h2>
        {m.renewals.length === 0 && <p className="muted" style={{ margin: 0 }}>В ближайшие 45 дней продлений нет.</p>}
        {m.renewals.map((r) => (
          <div key={`${r.trainer_id}-${r.kind}`} className="row" style={{ gridTemplateColumns: 'minmax(0,1fr) 70px 80px 140px' }}>
            <span style={{ display: 'flex', flexDirection: 'column' }}>
              <span style={{ fontWeight: 500 }}>
                {r.name}
                {r.kind === 'trial' && <span className="tiny muted"> · пробный</span>}
              </span>
              <span className="tiny muted">{r.reason}</span>
            </span>
            <span className="num">{shortDate(r.at)}</span>
            <b className="num">{rub(r.price)}</b>
            <span>
              <span className="badge" style={{ background: tint(RISK[r.risk].color), color: RISK[r.risk].color }}>
                {RISK[r.risk].label}
              </span>
            </span>
          </div>
        ))}
      </section>

      <section className="glass tile span-5" aria-labelledby="m-pay" style={{ gap: 6 }}>
        <h2 id="m-pay" style={{ paddingBottom: 8 }}>
          Последние оплаты
        </h2>
        {m.payments.length === 0 && <p className="muted" style={{ margin: 0 }}>Оплат пока не было.</p>}
        {m.payments.map((p, index) => (
          <div key={`${p.paid_at}-${index}`} className="row" style={{ gridTemplateColumns: '52px minmax(0,1fr) auto' }}>
            <span className="small muted num">{shortDate(p.paid_at)}</span>
            <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
              <span style={{ fontWeight: 500 }}>
                {p.name} · {p.plan === 'month' ? 'Pro, месяц' : p.plan}
              </span>
              <span className="tiny muted">через {p.bot ? `@${p.bot}` : 'основной бот'}</span>
            </span>
            <b className="num">{rub(p.price)}</b>
          </div>
        ))}
      </section>
    </>
  )
}

function Stat({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="well">
      <span className="tiny muted">{label}</span>
      <span className="num" style={{ fontSize: 22, fontWeight: 600 }}>
        {value}
      </span>
      <span className="tiny muted">{sub}</span>
    </div>
  )
}
