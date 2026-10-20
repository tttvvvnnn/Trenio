import { useEffect, useState, type ReactNode } from 'react'
import { put, type AdminPromo, type PromoSettings, type Terms } from '../api'
import { errorText, plural, rub } from '../format'
import { useData } from '../useData'
import { ErrorTile, PageTitle, Skeleton, type ScreenProps } from './common'

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
      <span className="small">{label}</span>
      {children}
      {hint && <span className="tiny muted">{hint}</span>}
    </label>
  )
}

// Форма с черновиком: сохраняем только по кнопке, данные экрана при этом не перетираются
function useDraft<T>(loaded: T | null) {
  const [draft, setDraft] = useState<T | null>(null)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)
  useEffect(() => {
    if (loaded && draft === null) setDraft(loaded)
  }, [loaded, draft])
  const dirty = draft !== null && loaded !== null && JSON.stringify(draft) !== JSON.stringify(loaded)
  const save = async (action: () => Promise<unknown>, done: string) => {
    setBusy(true)
    setNote(null)
    try {
      await action()
      setNote({ ok: true, text: done })
    } catch (reason) {
      setNote({ ok: false, text: errorText(reason) })
    } finally {
      setBusy(false)
    }
  }
  return { draft, setDraft, busy, note, dirty, save }
}

function SaveRow({ busy, dirty, note, onReset }: { busy: boolean; dirty: boolean; note: { ok: boolean; text: string } | null; onReset: () => void }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
      <button type="submit" className="btn" disabled={busy || !dirty}>
        {busy ? 'Сохраняю…' : 'Сохранить'}
      </button>
      {dirty && (
        <button type="button" className="btn secondary" onClick={onReset} disabled={busy}>
          Отменить правки
        </button>
      )}
      {note && (
        <span role={note.ok ? 'status' : 'alert'} className="small" style={{ color: note.ok ? 'var(--green)' : 'var(--red)' }}>
          {note.text}
        </span>
      )}
    </div>
  )
}

function TermsTile({ onUnauthorized }: ScreenProps) {
  const terms = useData<Terms>('/admin/plans', onUnauthorized)
  const { draft, setDraft, busy, note, dirty, save } = useDraft(terms.data)
  if (terms.error) return <ErrorTile text={terms.error} onRetry={terms.reload} />
  if (!draft || !terms.data) return <Skeleton span="span-6" />
  const set = (key: keyof Terms) => (event: React.ChangeEvent<HTMLInputElement>) =>
    setDraft({ ...draft, [key]: Number(event.target.value) })

  return (
    <section className="glass tile span-6" aria-labelledby="pl-terms">
      <div>
        <h2 id="pl-terms">Тариф</h2>
        <span className="small muted">Меняется сразу для всех: в Mini App, сообщениях бота и пользовательском соглашении.</span>
      </div>
      <form
        onSubmit={(event) => {
          event.preventDefault()
          void save(async () => {
            await put('/admin/plans', draft)
            terms.reload()
          }, 'Сохранено')
        }}
        style={{ display: 'flex', flexDirection: 'column', gap: 14 }}
      >
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12 }}>
          <Field label="Pro за 30 дней, ₽">
            <input className="field num" type="number" min={1} max={100000} required value={draft.price_month} onChange={set('price_month')} />
          </Field>
          <Field label="Пробный период, дней" hint="Только для новых тренеров">
            <input className="field num" type="number" min={0} max={365} required value={draft.trial_days} onChange={set('trial_days')} />
          </Field>
          <Field label="Клиентов бесплатно" hint="Уже добавленные не пропадут">
            <input className="field num" type="number" min={0} max={1000} required value={draft.free_client_limit} onChange={set('free_client_limit')} />
          </Field>
        </div>
        <p className="small muted" style={{ margin: 0 }}>
          Тренер видит: {draft.trial_days} {plural(draft.trial_days, 'день', 'дня', 'дней')} Pro бесплатно, потом до {draft.free_client_limit}{' '}
          {plural(draft.free_client_limit, 'клиента', 'клиентов', 'клиентов')} без оплаты или Pro за {rub(draft.price_month)} в месяц.
        </p>
        <SaveRow busy={busy} dirty={dirty} note={note} onReset={() => setDraft(terms.data)} />
      </form>
    </section>
  )
}

function PromoTile({ onUnauthorized }: ScreenProps) {
  const promo = useData<AdminPromo>('/admin/promo', onUnauthorized)
  const { draft, setDraft, busy, note, dirty, save } = useDraft<PromoSettings>(promo.data?.settings ?? null)
  if (promo.error) return <ErrorTile text={promo.error} onRetry={promo.reload} />
  if (!draft || !promo.data) return <Skeleton span="span-6" />
  const text = (key: keyof PromoSettings) => (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setDraft({ ...draft, [key]: event.target.value })
  const stats = promo.data.stats

  return (
    <section className="glass tile span-6" aria-labelledby="pl-promo">
      <div className="tile-head" style={{ alignItems: 'center' }}>
        <div>
          <h2 id="pl-promo">Промо TVPN</h2>
          <span className="small muted">Карточка на главном экране и строка в Профиле Mini App.</span>
        </div>
        <label className="chip" style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
          <input type="checkbox" checked={draft.enabled} onChange={(event) => setDraft({ ...draft, enabled: event.target.checked })} />
          {draft.enabled ? 'включено' : 'выключено'}
        </label>
      </div>
      <div className="kpis" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))' }}>
        {[
          ['Увидели', stats.shown],
          ['Закрыли', stats.dismissed],
          ['Открыли код', stats.claimed],
          ['Перешли', stats.opened],
        ].map(([label, value]) => (
          <div key={label} className="well">
            <span className="tiny muted">{label}</span>
            <b className="num" style={{ fontSize: 22, fontWeight: 600 }}>
              {value}
            </b>
          </div>
        ))}
      </div>
      <form
        onSubmit={(event) => {
          event.preventDefault()
          void save(async () => {
            await put('/admin/promo', draft)
            promo.reload()
          }, 'Сохранено')
        }}
        style={{ display: 'flex', flexDirection: 'column', gap: 12 }}
      >
        <Field label="Заголовок">
          <input className="field" required maxLength={80} value={draft.title} onChange={text('title')} />
        </Field>
        <Field label="Строка под заголовком">
          <input className="field" maxLength={160} value={draft.subtitle} onChange={text('subtitle')} />
        </Field>
        <Field label="Описание на экране с кодом">
          <textarea className="field" rows={3} maxLength={600} value={draft.text} onChange={text('text')} style={{ padding: 12, resize: 'vertical' }} />
        </Field>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12 }}>
          <Field label="Промокод">
            <input className="field" required maxLength={32} value={draft.code} onChange={text('code')} />
          </Field>
          <Field label="Текст кнопки">
            <input className="field" required maxLength={32} value={draft.button} onChange={text('button')} />
          </Field>
          <Field label="Показать через, дней" hint="после первого входа">
            <input
              className="field num"
              type="number"
              min={0}
              max={60}
              value={draft.delay_days}
              onChange={(event) => setDraft({ ...draft, delay_days: Number(event.target.value) })}
            />
          </Field>
        </div>
        <Field label="Ссылка кнопки" hint="https://, обычно бот в Telegram">
          <input className="field" required pattern="https://\S+" maxLength={200} value={draft.url} onChange={text('url')} />
        </Field>
        <SaveRow busy={busy} dirty={dirty} note={note} onReset={() => setDraft(promo.data!.settings)} />
      </form>
    </section>
  )
}

export default function Plans(props: ScreenProps) {
  return (
    <>
      <PageTitle sub="без деплоя" title="Тарифы и промо" />
      <TermsTile {...props} />
      <PromoTile {...props} />
    </>
  )
}
