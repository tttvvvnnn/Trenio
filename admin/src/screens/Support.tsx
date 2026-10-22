import { useState } from 'react'
import { post, type Ticket, type TicketStatus } from '../api'
import { ago, errorText, plural } from '../format'
import { useData } from '../useData'
import { Avatar, ErrorTile, Modal, PageTitle, Skeleton, TrainerLink, type ScreenProps } from './common'
import { TICKET_KIND } from './labels'


const FILTERS: { value: TicketStatus | 'all'; label: string }[] = [
  { value: 'new', label: 'Ждут ответа' },
  { value: 'answered', label: 'Отвеченные' },
  { value: 'closed', label: 'Закрытые' },
  { value: 'all', label: 'Все' },
]

function AnswerDialog({ ticket, onClose, onDone }: { ticket: Ticket; onClose: () => void; onDone: (note: string) => void }) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const send = async () => {
    setBusy(true)
    setError(null)
    try {
      await post(`/admin/support/${ticket.id}/answer`, { text })
      onDone(`Ответ для ${ticket.trainer_name} отправлен в бот`)
    } catch (reason) {
      setError(errorText(reason))
      setBusy(false)
    }
  }
  return (
    <Modal title={`Ответ: ${ticket.trainer_name}`} onClose={onClose}>
      <form
        onSubmit={(event) => {
          event.preventDefault()
          void send()
        }}
        style={{ display: 'flex', flexDirection: 'column', gap: 14 }}
      >
        <blockquote className="small" style={{ margin: 0, padding: '10px 14px', borderRadius: 14, background: 'var(--well)', whiteSpace: 'pre-wrap' }}>
          {ticket.text}
        </blockquote>
        <p className="small muted" style={{ margin: 0 }}>
          Придёт в бот с подписью «Ответ команды Trenio на ваше обращение» и цитатой сообщения.
        </p>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span className="sr">Текст ответа</span>
          <textarea
            className="field"
            rows={6}
            maxLength={3500}
            value={text}
            onChange={(event) => setText(event.target.value)}
            autoFocus
            style={{ padding: 12, resize: 'vertical' }}
          />
        </label>
        {error && (
          <p role="alert" className="small" style={{ margin: 0, color: 'var(--red)' }}>
            {error}
          </p>
        )}
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
          <button type="button" className="btn secondary" onClick={onClose} disabled={busy}>
            Отмена
          </button>
          <button type="submit" className="btn" disabled={busy || !text.trim()}>
            {busy ? 'Отправляю…' : 'Отправить в бот'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

export default function Support({ onUnauthorized }: ScreenProps) {
  const [filter, setFilter] = useState<TicketStatus | 'all'>('new')
  const all = useData<Ticket[]>('/admin/support', onUnauthorized)
  const [answering, setAnswering] = useState<Ticket | null>(null)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)

  const toggle = async (ticket: Ticket) => {
    setBusyId(ticket.id)
    setNote(null)
    try {
      await post(`/admin/support/${ticket.id}/status`, { closed: ticket.status !== 'closed' })
      all.reload()
    } catch (reason) {
      setNote({ ok: false, text: errorText(reason) })
    } finally {
      setBusyId(null)
    }
  }

  const tickets = all.data ?? []
  const count = (status: TicketStatus) => tickets.filter((ticket) => ticket.status === status).length
  const shown = filter === 'all' ? tickets : tickets.filter((ticket) => ticket.status === filter)
  const reviews = tickets.filter((ticket) => ticket.rating !== null)
  const average = reviews.length ? reviews.reduce((sum, ticket) => sum + (ticket.rating ?? 0), 0) / reviews.length : null
  const waiting = count('new')

  return (
    <>
      <PageTitle sub="вопросы и отзывы из Mini App" title="Обращения" />
      {all.error && <ErrorTile text={all.error} onRetry={all.reload} />}
      {!all.data && !all.error && <Skeleton />}
      {all.data && (
        <>
          <section className="glass tile span-4" style={{ gap: 6 }}>
            <span className="small muted">Ждут ответа</span>
            <b className="num" style={{ fontSize: 34, fontWeight: 600, color: waiting ? 'var(--coral)' : undefined }}>
              {waiting}
            </b>
            <span className="tiny muted">О новых сообщает бот, сразу как тренер отправил.</span>
          </section>
          <section className="glass tile span-4" style={{ gap: 6 }}>
            <span className="small muted">Всего обращений</span>
            <b className="num" style={{ fontSize: 34, fontWeight: 600 }}>
              {tickets.length}
            </b>
            <span className="tiny muted">
              отвечено {count('answered')}, закрыто без ответа {count('closed')}
            </span>
          </section>
          <section className="glass tile span-4" style={{ gap: 6 }}>
            <span className="small muted">Средняя оценка</span>
            <b className="num" style={{ fontSize: 34, fontWeight: 600 }}>
              {average === null ? '—' : average.toFixed(1).replace('.', ',')}
            </b>
            <span className="tiny muted">
              {reviews.length ? `${reviews.length} ${plural(reviews.length, 'отзыв', 'отзыва', 'отзывов')} с оценкой` : 'Отзывов с оценкой пока нет'}
            </span>
          </section>
          <section className="glass tile span-12" aria-labelledby="sp-list">
            <div className="tile-head" style={{ alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
              <h2 id="sp-list">Сообщения</h2>
              <div className="chips" role="group" aria-label="Показать">
                {FILTERS.map((item) => (
                  <button key={item.value} type="button" className="chip" aria-pressed={filter === item.value} onClick={() => setFilter(item.value)}>
                    {item.label}
                    {item.value !== 'all' && ` · ${count(item.value)}`}
                  </button>
                ))}
              </div>
            </div>
            {note && (
              <span role={note.ok ? 'status' : 'alert'} className="small" style={{ color: note.ok ? 'var(--green)' : 'var(--red)' }}>
                {note.text}
              </span>
            )}
            {shown.length === 0 && (
              <p className="small muted" style={{ margin: 0 }}>
                {filter === 'new' ? 'Все обращения разобраны.' : 'Здесь пока пусто.'}
              </p>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {shown.map((ticket) => {
                const kind = TICKET_KIND[ticket.kind]
                return (
                  <article key={ticket.id} className="well" style={{ gap: 10 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                      <Avatar id={ticket.trainer_id} name={ticket.trainer_name} url={null} size={34} />
                      <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0, flex: 1 }}>
                        <b style={{ fontWeight: 600 }}>
                          <TrainerLink id={ticket.trainer_id} name={ticket.trainer_name} />
                        </b>
                        <span className="tiny muted">
                          {ticket.username ? `@${ticket.username} · ` : ''}
                          {ago(ticket.created_at)}
                        </span>
                      </div>
                      <span className="badge" style={{ color: kind.color, background: `color-mix(in srgb, ${kind.color} var(--tint-alpha), transparent)` }}>
                        {kind.label}
                        {ticket.rating !== null && ` ${'★'.repeat(ticket.rating)}`}
                      </span>
                    </div>
                    <p style={{ margin: 0, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{ticket.text}</p>
                    {ticket.answer && (
                      <div className="small" style={{ padding: '10px 14px', borderRadius: 14, background: 'var(--panel)', border: '1px solid var(--edge)' }}>
                        <span className="tiny muted">Ваш ответ{ticket.answered_at ? `, ${ago(ticket.answered_at)}` : ''}</span>
                        <p style={{ margin: '4px 0 0', whiteSpace: 'pre-wrap' }}>{ticket.answer}</p>
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      {ticket.status !== 'closed' && (
                        <button type="button" className="btn small" onClick={() => setAnswering(ticket)}>
                          {ticket.answer ? 'Ответить ещё' : 'Ответить'}
                        </button>
                      )}
                      <button type="button" className="btn secondary small" onClick={() => void toggle(ticket)} disabled={busyId === ticket.id}>
                        {ticket.status === 'closed' ? 'Вернуть в работу' : 'Закрыть без ответа'}
                      </button>
                    </div>
                  </article>
                )
              })}
            </div>
          </section>
        </>
      )}
      {answering && (
        <AnswerDialog
          ticket={answering}
          onClose={() => setAnswering(null)}
          onDone={(text) => {
            setAnswering(null)
            setNote({ ok: true, text })
            all.reload()
          }}
        />
      )}
    </>
  )
}
