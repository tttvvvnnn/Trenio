import { useEffect, useState } from 'react'
import { post, type AdminClient, type ClientCard } from '../api'
import { ago, errorText, plural, shortDate, time, tint } from '../format'
import { useData } from '../useData'
import { Avatar, Bars, ErrorTile, Modal, PageTitle, Skeleton, type ScreenProps } from './common'

const COLUMNS = 'minmax(0,1.5fr) minmax(0,1fr) 90px 120px 120px'

const fullName = (c: { first_name: string; last_name: string | null }) =>
  [c.first_name, c.last_name].filter(Boolean).join(' ')

function subline(client: AdminClient): string {
  if (client.deleted) return 'аккаунт удалён'
  if (client.offline) return 'без Telegram, завёл тренер'
  return client.username ? `@${client.username}` : `№ ${client.id}`
}

type HistoryRow = ClientCard['history'][number]

function historyLabel(row: HistoryRow): { text: string; color: string } {
  if (row.status === 'cancelled') return { text: 'отменена', color: 'var(--muted)' }
  if (row.status === 'declined') return { text: 'отклонена', color: 'var(--muted)' }
  if (row.status === 'pending') return { text: 'ждёт тренера', color: 'var(--amber)' }
  if (row.attendance === 'attended') return { text: 'прошло', color: 'var(--green)' }
  if (row.attendance === 'missed_charged') return { text: 'пропуск, списано', color: 'var(--red)' }
  if (row.attendance === 'missed_free') return { text: 'пропуск', color: 'var(--amber)' }
  if (new Date(row.starts_at) > new Date()) return { text: 'впереди', color: 'var(--blue)' }
  return { text: 'не отмечено', color: 'var(--muted)' }
}

export default function Clients({ onUnauthorized }: ScreenProps) {
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [deleted, setDeleted] = useState(false)
  const [selected, setSelected] = useState<number | null>(null)

  // Ищет сервер: ждём паузу в наборе, чтобы не слать запрос на каждую букву
  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(query.trim()), 300)
    return () => window.clearTimeout(timer)
  }, [query])

  const params = new URLSearchParams()
  if (search) params.set('q', search)
  if (deleted) params.set('deleted', 'true')
  const suffix = params.toString()
  const clients = useData<AdminClient[]>(`/admin/clients${suffix ? `?${suffix}` : ''}`, onUnauthorized)

  return (
    <>
      <PageTitle sub={clients.data ? `${clients.data.length}${clients.data.length === 100 ? '+' : ''} в списке` : 'загрузка'} title="Клиенты">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
          <label className="glass" style={{ display: 'flex', alignItems: 'center', gap: 8, minHeight: 44, padding: '0 14px', borderRadius: 14, width: 320 }}>
            <span className="sr">Поиск клиента</span>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Имя, @username, Telegram ID или тренер"
              style={{ flex: 1, minWidth: 0, border: 0, background: 'transparent', font: 'inherit', fontSize: 14, color: 'var(--text)', outline: 'none' }}
            />
          </label>
          <div className="chips" role="group" aria-label="Какие аккаунты">
            <button type="button" className="chip" aria-pressed={!deleted} onClick={() => setDeleted(false)}>
              Действующие
            </button>
            <button type="button" className="chip" aria-pressed={deleted} onClick={() => setDeleted(true)}>
              Удалённые
            </button>
          </div>
        </div>
      </PageTitle>

      {clients.error && <ErrorTile text={clients.error} onRetry={clients.reload} />}
      {!clients.error && !clients.data && <Skeleton span={selected ? 'span-7' : 'span-12'} />}
      {clients.data && (
        <section
          className={`glass tile ${selected ? 'span-7' : 'span-12'}`}
          aria-label="Список клиентов"
          style={{ padding: '12px 16px 16px', gap: 0, overflowX: 'auto' }}
        >
          <div className="tiny muted" style={{ display: 'grid', gridTemplateColumns: COLUMNS, gap: 14, padding: '10px 12px', minWidth: 620 }}>
            <span>Клиент</span>
            <span>Тренер</span>
            <span style={{ textAlign: 'right' }}>Занятий</span>
            <span>Последнее</span>
            <span>В приложении</span>
          </div>
          {clients.data.length === 0 && (
            <p className="muted" style={{ padding: 12 }}>
              {search ? 'Никого не нашлось.' : deleted ? 'Удалённых аккаунтов нет.' : 'Клиентов пока нет.'}
            </p>
          )}
          {clients.data.map((client) => (
            <button
              key={client.id}
              type="button"
              aria-pressed={selected === client.id}
              onClick={() => setSelected(selected === client.id ? null : client.id)}
              style={{
                display: 'grid',
                gridTemplateColumns: COLUMNS,
                gap: 14,
                alignItems: 'center',
                minHeight: 60,
                minWidth: 620,
                padding: '0 12px',
                border: 0,
                borderRadius: 18,
                font: 'inherit',
                color: 'inherit',
                textAlign: 'left',
                background: selected === client.id ? 'var(--well)' : 'transparent',
              }}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
                <Avatar id={client.id} name={fullName(client)} url={client.avatar_url} size={36} />
                <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                  <span style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{fullName(client)}</span>
                  <span className="tiny muted">{subline(client)}</span>
                </span>
              </span>
              <span className="small" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {client.trainers.map((t) => t.name).join(', ')}
              </span>
              <span className="num" style={{ textAlign: 'right', fontWeight: 500 }}>
                {client.attended}
                <span className="tiny muted"> / {client.bookings}</span>
              </span>
              <span className="small muted">{client.last_booking_at ? shortDate(client.last_booking_at) : 'не было'}</span>
              <span className="small muted">{client.offline ? '—' : ago(client.last_seen_at)}</span>
            </button>
          ))}
        </section>
      )}

      {selected !== null && (
        <ClientPanel
          key={selected}
          id={selected}
          onUnauthorized={onUnauthorized}
          onClose={() => setSelected(null)}
          onDeleted={() => {
            setSelected(null)
            clients.reload()
          }}
        />
      )}
    </>
  )
}

function ClientPanel({
  id,
  onUnauthorized,
  onClose,
  onDeleted,
}: {
  id: number
  onUnauthorized: () => void
  onClose: () => void
  onDeleted: () => void
}) {
  const card = useData<ClientCard>(`/admin/clients/${id}`, onUnauthorized)
  const [confirming, setConfirming] = useState(false)

  if (card.error) return <ErrorTile text={card.error} onRetry={card.reload} />
  if (!card.data) return <Skeleton span="span-5" />
  const { client, links, history, activity } = card.data
  const canDelete = !client.deleted && !card.data.is_trainer

  return (
    <section className="glass tile span-5" aria-labelledby="client-name" style={{ position: 'sticky', top: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <Avatar id={client.id} name={fullName(client)} url={client.avatar_url} size={52} />
        <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0, flex: 1 }}>
          <h2 id="client-name">{fullName(client)}</h2>
          <span className="small muted">
            {subline(client)}
            {card.data.telegram_id !== null && ` · Telegram ID ${card.data.telegram_id}`}
          </span>
        </div>
        <button type="button" className="icon-btn" aria-label="Закрыть карточку" onClick={onClose}>
          <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      </div>

      {!client.offline && !client.deleted && (
        <div className="well">
          <span className="small muted">
            Заходил в приложение {activity.filter(Boolean).length} {plural(activity.filter(Boolean).length, 'день', 'дня', 'дней')} из 30 · {ago(client.last_seen_at)}
          </span>
          <Bars values={activity.map((day) => (day ? 1 : 0))} height={24} gap={2} label="Дни, когда клиент открывал приложение, за 30 дней" />
        </div>
      )}

      {links.map((link) => (
        <div key={link.trainer.id} className="well" style={{ gap: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
            <b style={{ fontWeight: 600 }}>{link.trainer.name}</b>
            <span className="tiny muted">клиент с {shortDate(link.since)}</span>
          </div>
          <div className="small" style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 14px' }}>
            <span>прошло <b className="num">{link.attended}</b></span>
            <span>пропусков <b className="num">{link.missed}</b></span>
            <span>отмен <b className="num">{link.cancelled}</b></span>
            {link.open_packages > 0 && <span>блоков <b className="num">{link.open_packages}</b></span>}
          </div>
          <span className="tiny muted">
            {link.next_booking_at ? `следующее ${shortDate(link.next_booking_at)} в ${time(link.next_booking_at)}` : 'следующей записи нет'}
            {link.last_booking_at && ` · последнее ${shortDate(link.last_booking_at)}`}
          </span>
        </div>
      ))}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <h3 className="small muted" style={{ margin: '4px 0 6px', fontWeight: 500 }}>
          История записей{history.length === 30 ? ', последние 30' : ''}
        </h3>
        {history.length === 0 && <p className="small muted" style={{ margin: 0 }}>Записей не было.</p>}
        {history.map((row, index) => {
          const label = historyLabel(row)
          return (
            <div key={`${row.starts_at}-${index}`} style={{ display: 'grid', gridTemplateColumns: '92px minmax(0,1fr) auto', gap: 10, alignItems: 'center', minHeight: 36 }}>
              <span className="small num">
                {shortDate(row.starts_at)} {time(row.starts_at)}
              </span>
              <span className="small" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {row.service}
                <span className="muted"> · {row.trainer}{row.created_by === 'client' ? ', сам' : ''}</span>
              </span>
              <span className="badge" style={{ background: tint(label.color), color: label.color }}>
                {label.text}
              </span>
            </div>
          )
        })}
      </div>

      {canDelete && (
        <div style={{ borderTop: '1px solid var(--edge)', paddingTop: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <span className="tiny muted">
            По запросу клиента: то же, что «Удалить аккаунт» в его профиле. Имя и фото стираются, будущие записи отменяются, у тренеров остаётся
            обезличенная история.
          </span>
          <div>
            <button type="button" className="btn danger small" onClick={() => setConfirming(true)}>
              Удалить данные клиента
            </button>
          </div>
        </div>
      )}
      {card.data.is_trainer && (
        <p className="tiny muted" style={{ margin: 0 }}>
          Этот человек ещё и тренер. Его данные удаляются вместе с аккаунтом тренера.
        </p>
      )}

      {confirming && <DeleteDialog card={card.data} onCancel={() => setConfirming(false)} onDeleted={onDeleted} />}
    </section>
  )
}

function DeleteDialog({ card, onCancel, onDeleted }: { card: ClientCard; onCancel: () => void; onDeleted: () => void }) {
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const upcoming = card.links.filter((link) => link.next_booking_at).length

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      await post(`/admin/clients/${card.client.id}/delete`, { reason })
      onDeleted()
    } catch (failure) {
      setError(errorText(failure))
      setBusy(false)
    }
  }

  return (
    <Modal title={`Удалить данные: ${fullName(card.client)}?`} onClose={onCancel}>
      <form
        onSubmit={(event) => {
          event.preventDefault()
          void submit()
        }}
        style={{ display: 'flex', flexDirection: 'column', gap: 14 }}
      >
        <p className="small" style={{ margin: 0 }}>
          Отменить это нельзя. Имя, фото, телефон и заметки тренеров о клиенте сотрутся
          {upcoming > 0 ? ', будущие записи отменятся, тренеры получат уведомление' : ''}. Записи и оплаты останутся у тренеров без имени.
        </p>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span className="small">Откуда запрос</span>
          <input
            className="field"
            required
            maxLength={500}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Например: письмо на почту 20.10"
            autoFocus
          />
          <span className="tiny muted">Попадёт в журнал действий.</span>
        </label>
        {error && (
          <p role="alert" className="small" style={{ margin: 0, color: 'var(--red)' }}>
            {error}
          </p>
        )}
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
          <button type="button" className="btn secondary" onClick={onCancel} disabled={busy}>
            Отмена
          </button>
          <button type="submit" className="btn danger" disabled={busy || !reason.trim()}>
            {busy ? 'Удаляю…' : 'Удалить навсегда'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
