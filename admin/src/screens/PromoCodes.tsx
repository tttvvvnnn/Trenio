import { useState } from 'react'
import { post, type CodeKind, type PromoCode, type Redemption } from '../api'
import { errorText, plural, rub, shortDate } from '../format'
import { useData } from '../useData'
import { ErrorTile, Modal, Skeleton, type ScreenProps } from './common'

const KINDS: { kind: CodeKind; label: string; unit: string; max: number }[] = [
  { kind: 'percent', label: 'Скидка, %', unit: '%', max: 99 },
  { kind: 'rubles', label: 'Скидка, ₽', unit: '₽', max: 100000 },
  { kind: 'days', label: 'Дни Pro', unit: 'дней', max: 366 },
]

function codeValue(code: Pick<PromoCode, 'kind' | 'value'>): string {
  if (code.kind === 'percent') return `−${code.value}% на оплату`
  if (code.kind === 'rubles') return `−${rub(code.value)} на оплату`
  return `${code.value} ${plural(code.value, 'день', 'дня', 'дней')} Pro`
}

function codeState(code: PromoCode, now: Date): { text: string; color: string } {
  if (!code.is_active) return { text: 'выключен', color: 'var(--muted)' }
  if (code.expires_at && new Date(code.expires_at) <= now) return { text: 'истёк', color: 'var(--muted)' }
  if (code.max_uses !== null && code.used + code.reserved >= code.max_uses) return { text: 'закончился', color: 'var(--amber)' }
  return { text: 'работает', color: 'var(--green)' }
}

const EMPTY = { code: '', kind: 'percent' as CodeKind, value: 20, max_uses: '', expires: '', note: '' }

function CreateForm({ onCreated }: { onCreated: (code: string) => void }) {
  const [form, setForm] = useState(EMPTY)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const kind = KINDS.find((item) => item.kind === form.kind)!
  const valid = /^[A-Za-zА-Яа-яЁё0-9_-]{3,32}$/.test(form.code.trim()) && form.value >= 1 && form.value <= kind.max

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      const created = await post<PromoCode>('/admin/promo-codes', {
        code: form.code.trim(),
        kind: form.kind,
        value: form.value,
        max_uses: form.max_uses ? Number(form.max_uses) : null,
        // Код действует весь последний день по Москве
        expires_at: form.expires ? `${form.expires}T23:59:59+03:00` : null,
        note: form.note.trim() || null,
      })
      setForm(EMPTY)
      onCreated(created.code)
    } catch (reason) {
      setError(errorText(reason))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        void submit()
      }}
      style={{ display: 'flex', flexDirection: 'column', gap: 12 }}
    >
      <div className="chips" role="group" aria-label="Что даёт код">
        {KINDS.map((item) => (
          <button
            key={item.kind}
            type="button"
            className="chip"
            aria-pressed={form.kind === item.kind}
            onClick={() => setForm({ ...form, kind: item.kind, value: Math.min(form.value, item.max) })}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12 }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span className="small">Код</span>
          <input
            className="field"
            required
            maxLength={32}
            value={form.code}
            onChange={(event) => setForm({ ...form, code: event.target.value.toUpperCase() })}
            placeholder="START20"
          />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span className="small">Размер, {kind.unit}</span>
          <input
            className="field num"
            type="number"
            min={1}
            max={kind.max}
            required
            value={form.value}
            onChange={(event) => setForm({ ...form, value: Number(event.target.value) })}
          />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span className="small">Сколько раз</span>
          <input
            className="field num"
            type="number"
            min={1}
            max={100000}
            value={form.max_uses}
            onChange={(event) => setForm({ ...form, max_uses: event.target.value })}
            placeholder="без лимита"
          />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span className="small">Действует до</span>
          <input className="field" type="date" value={form.expires} onChange={(event) => setForm({ ...form, expires: event.target.value })} />
        </label>
      </div>
      <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span className="small">Для кого и зачем</span>
        <input
          className="field"
          maxLength={200}
          value={form.note}
          onChange={(event) => setForm({ ...form, note: event.target.value })}
          placeholder="Например: личная скидка Анне за отзыв"
        />
        <span className="tiny muted">Видно только в админке. Личная скидка: код на 1 раз.</span>
      </label>
      <p className="small muted" style={{ margin: 0 }}>
        {form.kind === 'days'
          ? 'Тренер вводит код в Mini App на экране «Подписка», и Pro продлевается сразу.'
          : 'Тренер вводит код в Mini App на экране «Подписка», скидка применится к ближайшей оплате Pro.'}{' '}
        Один тренер может ввести код только один раз.
      </p>
      {error && (
        <p role="alert" className="small" style={{ margin: 0, color: 'var(--red)' }}>
          {error}
        </p>
      )}
      <div>
        <button type="submit" className="btn" disabled={busy || !valid}>
          {busy ? 'Создаю…' : 'Создать код'}
        </button>
      </div>
    </form>
  )
}

function RedemptionsDialog({ code, onClose, onUnauthorized }: { code: PromoCode; onClose: () => void } & ScreenProps) {
  const list = useData<Redemption[]>(`/admin/promo-codes/${code.id}/redemptions`, onUnauthorized)
  return (
    <Modal title={`Кто ввёл ${code.code}`} onClose={onClose}>
      {list.error && <p className="small" style={{ color: 'var(--red)' }}>{list.error}</p>}
      {!list.data && !list.error && <p className="small muted">Загружаю…</p>}
      {list.data?.length === 0 && <p className="small muted">Пока никто.</p>}
      <div className="rows">
        {list.data?.map((row) => (
          <div key={row.trainer_id} className="row" style={{ gridTemplateColumns: 'minmax(0, 1fr) auto' }}>
            <span>{row.name}</span>
            <span className="small muted" style={{ textAlign: 'right' }}>
              {row.status === 'used' ? `использован ${shortDate(row.used_at ?? row.created_at)}` : `введён ${shortDate(row.created_at)}, ждёт оплаты`}
            </span>
          </div>
        ))}
      </div>
    </Modal>
  )
}

export function PromoCodesTile({ onUnauthorized }: ScreenProps) {
  const codes = useData<PromoCode[]>('/admin/promo-codes', onUnauthorized)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)
  const [open, setOpen] = useState<PromoCode | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  if (codes.error) return <ErrorTile text={codes.error} onRetry={codes.reload} />
  if (!codes.data) return <Skeleton />
  const now = new Date()

  const toggle = async (code: PromoCode) => {
    setBusyId(code.id)
    setNote(null)
    try {
      await post(`/admin/promo-codes/${code.id}/active`, { active: !code.is_active })
      setNote({ ok: true, text: `${code.code} ${code.is_active ? 'выключен' : 'включён'}` })
      codes.reload()
    } catch (reason) {
      setNote({ ok: false, text: errorText(reason) })
    } finally {
      setBusyId(null)
    }
  }

  return (
    <section className="glass tile span-12" aria-labelledby="pl-codes">
      <div>
        <h2 id="pl-codes">Промокоды для тренеров</h2>
        <span className="small muted">Скидка на оплату Pro или дни Pro бесплатно.</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 380px), 1fr))', gap: 24, alignItems: 'start' }}>
        <CreateForm
          onCreated={(code) => {
            setNote({ ok: true, text: `Код ${code} создан` })
            codes.reload()
          }}
        />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0 }}>
          {note && (
            <span role={note.ok ? 'status' : 'alert'} className="small" style={{ color: note.ok ? 'var(--green)' : 'var(--red)' }}>
              {note.text}
            </span>
          )}
          {codes.data.length === 0 && <p className="small muted" style={{ margin: 0 }}>Кодов пока нет. Создайте первый слева.</p>}
          {codes.data.map((code) => {
            const state = codeState(code, now)
            return (
              <div key={code.id} className="well" style={{ gap: 6 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <b className="num" style={{ fontWeight: 600, letterSpacing: '0.04em' }}>
                    {code.code}
                  </b>
                  <span className="tiny" style={{ color: state.color }}>
                    {state.text}
                  </span>
                </div>
                <span className="small">{codeValue(code)}</span>
                <span className="tiny muted">
                  использован {code.used}
                  {code.max_uses !== null && ` из ${code.max_uses}`}
                  {code.reserved > 0 && ` · ждут оплаты ${code.reserved}`}
                  {code.expires_at && ` · до ${shortDate(code.expires_at)}`}
                </span>
                {code.note && <span className="tiny muted">{code.note}</span>}
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 4 }}>
                  <button type="button" className="btn secondary small" onClick={() => setOpen(code)} disabled={code.used + code.reserved === 0}>
                    Кто ввёл
                  </button>
                  <button type="button" className="btn secondary small" onClick={() => void toggle(code)} disabled={busyId === code.id}>
                    {code.is_active ? 'Выключить' : 'Включить'}
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      </div>
      {open && <RedemptionsDialog code={open} onClose={() => setOpen(null)} onUnauthorized={onUnauthorized} />}
    </section>
  )
}
