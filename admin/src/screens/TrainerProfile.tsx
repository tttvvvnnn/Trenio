import { useEffect, useState, type ReactNode } from 'react'
import { post, type ClientPage, type TrainerEventKind, type TrainerProfile as Profile } from '../api'
import { ago, errorText, plural, rub, shortDate, tint } from '../format'
import { clientHref, go, href } from '../route'
import { useData } from '../useData'
import { Avatar, BackLink, Bars, ErrorTile, Skeleton, TrainerLink, type ScreenProps } from './common'
import { auditText, codeValue, planText, STATE_COLOR, STATE_LABEL, TICKET_KIND } from './labels'
import { TrainerActionDialog, type TrainerAction } from './TrainerActions'

const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

const PAYMENT_STATUS: Record<Profile['payments'][number]['status'], { text: string; color: string }> = {
  paid: { text: 'оплачено', color: 'var(--green)' },
  pending: { text: 'не оплатил', color: 'var(--amber)' },
  canceled: { text: 'отменена', color: 'var(--muted)' },
}

const EVENT_COLOR: Record<TrainerEventKind, string> = {
  joined: 'var(--blue)',
  onboarded: 'var(--blue)',
  first_client: 'var(--green)',
  first_client_booking: 'var(--green)',
  first_package: 'var(--green)',
  paid: 'var(--green)',
  promo: 'var(--violet)',
  ticket: 'var(--amber)',
  referral: 'var(--violet)',
  trial_ended: 'var(--red)',
  pro_ended: 'var(--red)',
}

const fullName = (c: { first_name: string; last_name: string | null }) => [c.first_name, c.last_name].filter(Boolean).join(' ')

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '130px minmax(0,1fr)', gap: 10, alignItems: 'baseline', minHeight: 30 }}>
      <span className="small muted">{label}</span>
      <span className="small" style={{ overflowWrap: 'anywhere' }}>
        {children}
      </span>
    </div>
  )
}

function Number_({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="well">
      <span className="small muted">{label}</span>
      {/* Длинное значение, вроде «сегодня 11:05», мельче, чтобы влезало в строку */}
      <span className="num" style={{ fontSize: typeof value === 'string' && value.length > 8 ? 19 : 24, fontWeight: 600, lineHeight: 1.3 }}>
        {value}
      </span>
      {sub && <span className="tiny muted">{sub}</span>}
    </div>
  )
}

// Часы по дням недели: «Пн 10:00–14:00, 16:00–20:00»
function hoursByDay(hours: Profile['hours']): [string, string][] {
  const days = new Map<number, string[]>()
  for (const h of hours) days.set(h.weekday, [...(days.get(h.weekday) ?? []), `${h.start}–${h.end}`])
  return [...days.entries()].map(([day, windows]) => [WEEKDAYS[day], windows.join(', ')])
}

export default function TrainerProfile({ id, onUnauthorized }: { id: number } & ScreenProps) {
  const profile = useData<Profile>(`/admin/trainers/${id}`, onUnauthorized)
  const clients = useData<ClientPage>(`/admin/clients?trainer_id=${id}&sort=seen`, onUnauthorized)
  const [action, setAction] = useState<TrainerAction | null>(null)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  // В фигурных скобках: новые браузеры возвращают из scrollTo промис, и React принял бы его за функцию очистки
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [])

  if (profile.error) return <ErrorTile text={profile.error} onRetry={profile.reload} />
  if (!profile.data) {
    return (
      <>
        <Skeleton span="span-4" />
        <Skeleton span="span-8" />
        <Skeleton span="span-12" />
      </>
    )
  }
  const p = profile.data
  const t = p.trainer
  const seenDays = p.activity.filter(Boolean).length
  const pending = p.tickets.filter((ticket) => ticket.status === 'new').length
  // Шаги тренера и действия админа одной лентой, свежие сверху
  const history: { at: string; color: string; text: ReactNode }[] = [
    ...p.events.map((event) => ({
      at: event.at,
      color: EVENT_COLOR[event.kind],
      text: event.trainer_id ? <TrainerLink id={event.trainer_id} name={event.text} /> : event.text,
    })),
    ...p.audit.map((entry) => ({ at: entry.created_at, color: 'var(--muted)', text: <span className="muted">Админ: {auditText(entry)}</span> })),
  ].sort((a, b) => b.at.localeCompare(a.at))

  const toggle = async () => {
    const enable = t.state === 'disabled'
    const question = enable
      ? `Вернуть доступ тренеру ${t.display_name}?`
      : `Отключить ${t.display_name}? Тренер и его клиенты не смогут пользоваться Trenio, данные сохранятся.`
    if (!window.confirm(question)) return
    setBusy(true)
    setNote(null)
    try {
      await post(`/admin/trainers/${t.id}/active`, { active: enable })
      setNote({ ok: true, text: enable ? 'Доступ возвращён' : 'Тренер отключён' })
      profile.reload()
    } catch (reason) {
      setNote({ ok: false, text: errorText(reason) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="page-title">
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, minWidth: 0 }}>
          <Avatar id={t.id} name={t.display_name} url={t.avatar_url} size={64} />
          <div style={{ minWidth: 0 }}>
            <BackLink href="#/trainers">Все тренеры</BackLink>
            <h1 style={{ overflowWrap: 'anywhere' }}>{t.display_name}</h1>
            <span style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
              <span className="badge" style={{ background: tint(STATE_COLOR[t.state]), color: STATE_COLOR[t.state] }}>
                {t.is_admin ? 'админ' : STATE_LABEL[t.state]}
              </span>
              {!t.is_admin && <span className="small muted">{planText(t)}</span>}
            </span>
          </div>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {t.user.username && (
            <a className="btn secondary small" href={`https://t.me/${t.user.username}`} target="_blank" rel="noreferrer">
              Написать в личку
            </a>
          )}
          <button type="button" className="btn secondary small" onClick={() => setAction('message')}>
            Сообщение в бот
          </button>
          {!t.is_admin && (
            <>
              <button type="button" className="btn secondary small" onClick={() => setAction('pro')}>
                Pro в подарок
              </button>
              <button type="button" className="btn secondary small" disabled={busy} onClick={() => void toggle()}>
                {t.state === 'disabled' ? 'Вернуть доступ' : 'Отключить'}
              </button>
              <button type="button" className="btn danger small" onClick={() => setAction('delete')}>
                Удалить…
              </button>
            </>
          )}
        </div>
      </div>

      {note && (
        <p className="notice span-12" role={note.ok ? 'status' : 'alert'} style={{ color: note.ok ? 'var(--green)' : 'var(--red)', margin: 0 }}>
          {note.text}
        </p>
      )}
      {action && (
        <TrainerActionDialog
          action={action}
          trainer={t}
          onClose={() => setAction(null)}
          onDone={(text) => {
            setAction(null)
            if (action === 'delete') {
              go(href('trainers'))
              return
            }
            setNote({ ok: true, text })
            profile.reload()
          }}
        />
      )}

      <section className="glass tile span-4" aria-labelledby="tp-about" style={{ gap: 2 }}>
        <h2 id="tp-about" style={{ paddingBottom: 8 }}>
          О тренере
        </h2>
        <Fact label="Telegram">
          {t.user.username ? `@${t.user.username}` : 'без username'}
          {p.telegram_id !== null && <span className="muted"> · ID {p.telegram_id}</span>}
        </Fact>
        <Fact label="Номер">№ {t.id}</Fact>
        <Fact label="В Trenio">с {shortDate(t.since)}</Fact>
        <Fact label="Пришёл">{p.referred_by ? <>по ссылке <TrainerLink id={p.referred_by.id} name={p.referred_by.name} /></> : 'по приглашению админа'}</Fact>
        {p.referrals.length > 0 && (
          <Fact label={`Пригласил (${p.referrals.length})`}>
            {p.referrals.map((r, index) => (
              <span key={r.id}>
                {index > 0 && ', '}
                <TrainerLink id={r.id} name={r.name} />
              </span>
            ))}
          </Fact>
        )}
        {p.balance > 0 && <Fact label="Баланс">{rub(p.balance)}</Fact>}
        <Fact label="Часовой пояс">{t.timezone}</Fact>
        {p.address && <Fact label="Адрес">{p.address}</Fact>}
        <Fact label="Записи">{p.auto_confirm ? 'подтверждаются сразу' : 'ждут подтверждения'}</Fact>
        <Fact label="Отмена клиентом">не позже чем за {p.cancel_hours} ч</Fact>
      </section>

      <section className="glass tile span-8" aria-labelledby="tp-work">
        <h2 id="tp-work">Как работает</h2>
        <div className="kpis">
          <Number_
            label="Клиентов"
            value={t.clients}
            sub={t.clients_new_week > 0 ? <span style={{ color: 'var(--green)' }}>+{t.clients_new_week} за неделю</span> : 'новых за неделю нет'}
          />
          <Number_ label="Занятий за 30 дней" value={t.bookings_month} sub={`прошло ${t.attended_month}`} />
          <Number_ label="Последнее занятие" value={t.last_booking_at ? shortDate(t.last_booking_at) : '—'} sub={`активных услуг ${t.services}`} />
          <Number_ label="Заходил" value={ago(t.last_seen_at)} sub={t.streak > 1 ? `${t.streak} ${plural(t.streak, 'день', 'дня', 'дней')} подряд` : undefined} />
        </div>
        <div className="well">
          <span className="small muted">
            Открывал приложение {seenDays} {plural(seenDays, 'день', 'дня', 'дней')} из 30
          </span>
          <Bars values={p.activity.map((day) => (day ? 1 : 0))} height={28} gap={3} label="Дни, когда тренер открывал приложение, за 30 дней" />
        </div>
        <span className="tiny muted">
          За две недели сам поставил {t.bookings_created} {plural(t.bookings_created, 'запись', 'записи', 'записей')}, отметил{' '}
          {t.marks} {plural(t.marks, 'занятие', 'занятия', 'занятий')}.
        </span>
      </section>

      <section className="glass tile span-7" aria-labelledby="tp-clients" style={{ gap: 6 }}>
        <div className="tile-head" style={{ paddingBottom: 6 }}>
          <h2 id="tp-clients">Клиенты</h2>
          {clients.data && clients.data.total > 0 && (
            <a href={href('clients', null, { trainer: t.id })} className="small">
              Все {clients.data.total} в разделе «Клиенты»
            </a>
          )}
        </div>
        {clients.error && <p className="small" style={{ color: 'var(--red)', margin: 0 }}>{clients.error}</p>}
        {clients.data?.total === 0 && <p className="muted" style={{ margin: 0 }}>Клиентов пока нет.</p>}
        {clients.data?.items.slice(0, 8).map((client) => (
          <a
            key={client.id}
            href={clientHref(client.id)}
            className="row person-link"
            style={{ gridTemplateColumns: 'minmax(0,1fr) auto auto' }}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
              <Avatar id={client.id} name={fullName(client)} url={client.avatar_url} size={32} />
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 500 }}>{fullName(client)}</span>
            </span>
            <span className="num small" style={{ textAlign: 'right' }}>
              {client.attended}
              <span className="tiny muted"> / {client.bookings}</span>
            </span>
            <span className="small muted">{client.offline ? 'без Telegram' : ago(client.last_seen_at)}</span>
          </a>
        ))}
      </section>

      <section className="glass tile span-5" aria-labelledby="tp-services" style={{ gap: 6 }}>
        <h2 id="tp-services" style={{ paddingBottom: 6 }}>
          Услуги и часы
        </h2>
        {p.services.length === 0 && <p className="muted" style={{ margin: 0 }}>Услуг нет.</p>}
        {p.services.map((s, index) => (
          <div key={index} className="row" style={{ gridTemplateColumns: 'minmax(0,1fr) auto', opacity: s.is_active ? 1 : 0.55 }}>
            <span style={{ overflowWrap: 'anywhere' }}>{s.name}</span>
            <span className="small muted">
              {s.duration_min} мин{s.capacity > 1 ? ` · до ${s.capacity} чел.` : ''}
              {!s.is_active && ' · выключена'}
            </span>
          </div>
        ))}
        <h3 className="small muted" style={{ margin: '12px 0 4px', fontWeight: 500 }}>
          Рабочие часы по неделям
        </h3>
        {p.hours.length === 0 && <p className="small muted" style={{ margin: 0 }}>Не заданы.</p>}
        {hoursByDay(p.hours).map(([day, windows]) => (
          <div key={day} className="small" style={{ display: 'grid', gridTemplateColumns: '32px minmax(0,1fr)', gap: 8 }}>
            <b style={{ fontWeight: 600 }}>{day}</b>
            <span className="num">{windows}</span>
          </div>
        ))}
      </section>

      <section className="glass tile span-6" aria-labelledby="tp-money" style={{ gap: 6 }}>
        <div className="tile-head" style={{ paddingBottom: 6 }}>
          <h2 id="tp-money">Оплаты Pro</h2>
          <span className="small muted">всего {rub(p.paid_total)}</span>
        </div>
        {p.payments.length === 0 && <p className="muted" style={{ margin: 0 }}>Не платил.</p>}
        {p.payments.map((payment, index) => {
          const state = PAYMENT_STATUS[payment.status]
          return (
            <div key={index} className="row" style={{ gridTemplateColumns: '60px minmax(0,1fr) auto auto' }}>
              <span className="small muted num">{shortDate(payment.paid_at ?? payment.created_at)}</span>
              <span className="small">
                {payment.plan === 'month' ? 'Pro, месяц' : payment.plan === 'year' ? 'Pro, год' : payment.plan}
                {payment.balance_used > 0 && <span className="muted"> · {rub(payment.balance_used)} с баланса</span>}
              </span>
              <b className="num">{rub(payment.price)}</b>
              <span className="badge" style={{ background: tint(state.color), color: state.color }}>
                {state.text}
              </span>
            </div>
          )
        })}
        {p.promos.length > 0 && (
          <>
            <h3 className="small muted" style={{ margin: '12px 0 4px', fontWeight: 500 }}>
              Промокоды
            </h3>
            {p.promos.map((promo) => (
              <div key={promo.code_id} className="row" style={{ gridTemplateColumns: 'auto minmax(0,1fr) auto' }}>
                <code>{promo.code}</code>
                <span className="small muted">{codeValue(promo)}</span>
                <span className="small muted">
                  {promo.status === 'used' ? `использован ${shortDate(promo.used_at ?? promo.created_at)}` : `введён ${shortDate(promo.created_at)}, ждёт оплаты`}
                </span>
              </div>
            ))}
          </>
        )}
      </section>

      <section className="glass tile span-6" aria-labelledby="tp-support" style={{ gap: 8 }}>
        <div className="tile-head">
          <h2 id="tp-support">Обращения</h2>
          {pending > 0 && (
            <a href="#/support" className="small">
              ждут ответа: {pending}
            </a>
          )}
        </div>
        {p.tickets.length === 0 && <p className="muted" style={{ margin: 0 }}>Не писал.</p>}
        {p.tickets.slice(0, 5).map((ticket) => {
          const kind = TICKET_KIND[ticket.kind]
          return (
            <div key={ticket.id} className="well" style={{ gap: 6 }}>
              <span style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <span className="badge" style={{ color: kind.color, background: tint(kind.color) }}>
                  {kind.label}
                  {ticket.rating !== null && ` ${'★'.repeat(ticket.rating)}`}
                </span>
                <span className="tiny muted">
                  {ago(ticket.created_at)} · {ticket.status === 'new' ? 'ждёт ответа' : ticket.status === 'answered' ? 'отвечено' : 'закрыто'}
                </span>
              </span>
              <p className="small" style={{ margin: 0, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
                {ticket.text}
              </p>
            </div>
          )
        })}
      </section>

      <section className="glass tile span-12" aria-labelledby="tp-history" style={{ gap: 6 }}>
        <div className="tile-head" style={{ paddingBottom: 6 }}>
          <h2 id="tp-history">История</h2>
          <span className="small muted">шаги тренера, оплаты, обращения и действия админа</span>
        </div>
        {history.map((item, index) => (
          <div key={index} className="row" style={{ gridTemplateColumns: '18px 110px minmax(0,1fr)' }}>
            <span className="dot" aria-hidden="true" style={{ background: item.color }} />
            <span className="small muted num">{shortDate(item.at)}</span>
            <span className="small">{item.text}</span>
          </div>
        ))}
      </section>
    </>
  )
}
