import { useState } from 'react'
import { post, type BroadcastItem, type Segment } from '../api'
import { errorText, plural, shortDate, time } from '../format'
import { useData } from '../useData'
import { ErrorTile, Modal, PageTitle, Skeleton, type ScreenProps } from './common'

const SEGMENTS: { id: Segment; label: string; hint: string }[] = [
  { id: 'all', label: 'Все тренеры', hint: 'кроме отключённых и админов' },
  { id: 'trial', label: 'На пробном', hint: 'пробный период ещё идёт' },
  { id: 'pro', label: 'С Pro', hint: 'оплатили или получили в подарок' },
  { id: 'free', label: 'Бесплатный тариф', hint: 'пробный кончился, Pro нет' },
  { id: 'not_set_up', label: 'Не настроились', hint: 'нет услуги или рабочих часов' },
  { id: 'quiet', label: 'Затихли', hint: 'нет записей две недели' },
]

const segmentLabel = (id: string) => SEGMENTS.find((s) => s.id === id)?.label ?? id

export default function Broadcasts({ onUnauthorized }: ScreenProps) {
  const history = useData<BroadcastItem[]>('/admin/broadcasts', onUnauthorized)
  const [segment, setSegment] = useState<Segment>('all')
  const audience = useData<{ count: number; names: string[] }>(`/admin/broadcasts/audience?segment=${segment}`, onUnauthorized)
  const [text, setText] = useState('')
  const [withButton, setWithButton] = useState(true)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)
  const [confirming, setConfirming] = useState(false)

  const run = async (action: () => Promise<string>) => {
    setBusy(true)
    setNote(null)
    try {
      setNote({ ok: true, text: await action() })
    } catch (reason) {
      setNote({ ok: false, text: errorText(reason) })
    } finally {
      setBusy(false)
    }
  }

  const test = () =>
    run(async () => {
      await post('/admin/broadcasts/test', { text, with_button: withButton })
      return 'Тестовое сообщение у вас в боте'
    })

  const send = () =>
    run(async () => {
      setConfirming(false)
      const item = await post<BroadcastItem>('/admin/broadcasts', { text, segment, with_button: withButton })
      setText('')
      history.reload()
      return `Отправляется: ${item.recipients} ${plural(item.recipients, 'тренер', 'тренера', 'тренеров')}`
    })

  const count = audience.data?.count ?? 0

  return (
    <>
      <PageTitle sub="сообщение в бот от команды Trenio" title="Рассылки" />

      <section className="glass tile span-7" aria-labelledby="bc-new">
        <h2 id="bc-new">Новая рассылка</h2>
        <div className="chips" role="group" aria-label="Кому">
          {SEGMENTS.map((item) => (
            <button key={item.id} type="button" className="chip" aria-pressed={segment === item.id} onClick={() => setSegment(item.id)} title={item.hint}>
              {item.label}
            </button>
          ))}
        </div>
        <span className="small muted">
          {SEGMENTS.find((s) => s.id === segment)?.hint}:{' '}
          {audience.data ? (
            <b style={{ color: 'var(--text)' }}>
              {count} {plural(count, 'тренер', 'тренера', 'тренеров')}
            </b>
          ) : (
            '…'
          )}
          {audience.data && count > 0 && count <= 8 && ` (${audience.data.names.join(', ')})`}
        </span>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span className="sr">Текст рассылки</span>
          <textarea
            className="field"
            rows={8}
            maxLength={3500}
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="Что нового в Trenio, акция или просьба об отзыве"
            style={{ padding: 12, resize: 'vertical' }}
          />
          <span className="tiny muted" style={{ textAlign: 'right' }}>
            {text.length} / 3500
          </span>
        </label>
        <label className="small" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <input type="checkbox" checked={withButton} onChange={(event) => setWithButton(event.target.checked)} />
          Кнопка «Открыть Trenio» под сообщением
        </label>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          <button type="button" className="btn secondary" disabled={busy || !text.trim()} onClick={() => void test()}>
            Отправить себе
          </button>
          <button type="button" className="btn" disabled={busy || !text.trim() || count === 0} onClick={() => setConfirming(true)}>
            Отправить {count > 0 ? `${count} ${plural(count, 'тренеру', 'тренерам', 'тренерам')}` : ''}
          </button>
          {note && (
            <span role={note.ok ? 'status' : 'alert'} className="small" style={{ color: note.ok ? 'var(--green)' : 'var(--red)' }}>
              {note.text}
            </span>
          )}
        </div>
      </section>

      <section className="glass tile span-5" aria-labelledby="bc-hist">
        <h2 id="bc-hist">Отправленные</h2>
        {history.error && <ErrorTile text={history.error} onRetry={history.reload} />}
        {!history.data && !history.error && <Skeleton span="span-12" />}
        {history.data?.length === 0 && <p className="muted" style={{ margin: 0 }}>Рассылок ещё не было.</p>}
        {history.data?.map((item) => (
          <div key={item.id} className="well" style={{ gap: 6 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
              <b style={{ fontWeight: 600 }}>{segmentLabel(item.segment)}</b>
              <span className="tiny muted">
                {shortDate(item.created_at)} {time(item.created_at)}
              </span>
            </div>
            <span className="small" style={{ whiteSpace: 'pre-wrap', display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
              {item.text}
            </span>
            <span className="tiny muted">
              доставлено {item.sent} из {item.recipients}
              {item.pending > 0 && ` · в очереди ${item.pending}`}
              {item.failed > 0 && <span style={{ color: 'var(--red)' }}> · не дошло {item.failed}</span>}
            </span>
          </div>
        ))}
      </section>

      {confirming && (
        <Modal title={`Отправить ${count} ${plural(count, 'тренеру', 'тренерам', 'тренерам')}?`} onClose={() => setConfirming(false)}>
          <p className="small" style={{ margin: '0 0 14px' }}>
            Сообщение уйдёт сразу, отозвать его нельзя. Сегмент: {segmentLabel(segment).toLowerCase()}.
          </p>
          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
            <button type="button" className="btn secondary" onClick={() => setConfirming(false)}>
              Отмена
            </button>
            <button type="button" className="btn" onClick={() => void send()} autoFocus>
              Отправить
            </button>
          </div>
        </Modal>
      )}
    </>
  )
}
