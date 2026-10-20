import { useEffect, useId, useState } from 'react'

import { errorText, fetchSupport, sendSupport, type SupportKind, type SupportTicket } from '../api'
import { dateTime } from '../format'
import { haptic } from '../telegram'
import { Chips, ErrorText, Section } from '../ui/kit'
import { MainButton } from '../ui/native'
import Screen from '../ui/Screen'

type Props = {
  timezone: string
  onBack: () => void
}

// Как на сервере
const MAX_TEXT = 3000

const KINDS: readonly (readonly [SupportKind, string])[] = [
  ['question', 'Вопрос'],
  ['problem', 'Проблема'],
  ['idea', 'Идея'],
  ['review', 'Отзыв'],
]

const RATINGS: readonly (readonly [number, string])[] = [1, 2, 3, 4, 5].map(
  (n) => [n, '★'.repeat(n)] as const,
)

const PLACEHOLDER: Record<SupportKind, string> = {
  question: 'Что хотите узнать?',
  problem: 'Что случилось и на каком экране? Чем подробнее, тем быстрее починим',
  idea: 'Чего не хватает в Trenio?',
  review: 'Что нравится, что мешает',
}

const KIND_TITLE = Object.fromEntries(KINDS) as Record<SupportKind, string>

function statusText(ticket: SupportTicket): string {
  if (ticket.status === 'answered') return 'Ответили'
  if (ticket.status === 'closed') return 'Прочитали'
  return 'Ждёт ответа'
}

/** «Написать нам»: вопрос, проблема, идея или отзыв команде Trenio. Ответ придёт в бот. */
export default function Support({ timezone, onBack }: Props) {
  const id = useId()
  const [kind, setKind] = useState<SupportKind>('question')
  const [rating, setRating] = useState<number | null>(null)
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)
  const [history, setHistory] = useState<SupportTicket[]>([])

  useEffect(() => {
    fetchSupport()
      .then(setHistory)
      .catch(() => {})
  }, [])

  const ready = text.trim() !== '' && (kind !== 'review' || rating !== null)

  async function submit() {
    if (sending || !ready) return
    setSending(true)
    setError(null)
    try {
      const ticket = await sendSupport(kind, text.trim(), kind === 'review' ? rating : null)
      haptic.success()
      setHistory((all) => [ticket, ...all])
      setText('')
      setRating(null)
      setSent(true)
    } catch (err) {
      haptic.error()
      setError(errorText(err))
    } finally {
      setSending(false)
    }
  }

  return (
    <Screen title="Написать нам" onBack={onBack}>
      {sent && (
        <p className="card-hint done">
          Спасибо! Сообщение у команды Trenio. Ответ придёт в этот бот.
        </p>
      )}
      <Section title="О чём">
        <Chips
          label="О чём сообщение"
          value={kind}
          options={KINDS}
          onChange={(value) => {
            setKind(value)
            setSent(false)
          }}
        />
      </Section>
      {kind === 'review' && (
        <Section title="Оценка">
          <Chips label="Оценка" value={rating ?? 0} options={RATINGS} onChange={setRating} />
        </Section>
      )}
      <section className="section">
        <label className="section-title" htmlFor={id}>
          Сообщение
        </label>
        <div className="group">
          <textarea
            id={id}
            className="field-input"
            placeholder={PLACEHOLDER[kind]}
            maxLength={MAX_TEXT}
            value={text}
            onChange={(event) => {
              setText(event.target.value)
              setSent(false)
            }}
          />
        </div>
        <p className="section-footer">Читаем каждое сообщение. Ответ придёт в бот Trenio.</p>
      </section>
      {error && <ErrorText>{error}</ErrorText>}
      {history.length > 0 && (
        <Section title="Вы писали">
          {history.map((ticket) => (
            <div key={ticket.id} className="support-item">
              <div className="support-meta">
                <span>
                  {KIND_TITLE[ticket.kind]}
                  {ticket.rating ? ` ${'★'.repeat(ticket.rating)}` : ''} ·{' '}
                  {dateTime(ticket.created_at, timezone)}
                </span>
                <span
                  className={
                    ticket.status === 'answered' ? 'support-status done' : 'support-status'
                  }
                >
                  {statusText(ticket)}
                </span>
              </div>
              <p className="support-text">{ticket.text}</p>
              {ticket.answer && (
                <p className="support-answer">
                  <b>Ответ Trenio</b>
                  {ticket.answer}
                </p>
              )}
            </div>
          ))}
        </Section>
      )}
      <MainButton
        text="Отправить"
        onClick={() => void submit()}
        disabled={!ready}
        loading={sending}
      />
    </Screen>
  )
}
