import { useEffect, useState, type FormEvent } from 'react'

import {
  createException,
  deleteException,
  fetchExceptions,
  type ExceptionKind,
  type ScheduleException,
} from '../api'
import { addDays, dayTitle, hhmm, localDate } from '../format'

// Сколько дней вперёд показываем правки
const HORIZON_DAYS = 90

type Props = {
  timezone: string
}

export default function Days({ timezone }: Props) {
  const today = localDate(new Date(), timezone)
  const [items, setItems] = useState<ScheduleException[] | null>(null)
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function reload() {
    try {
      setItems(await fetchExceptions(today, addDays(today, HORIZON_DAYS)))
    } catch (err) {
      setError(String(err))
    }
  }

  useEffect(() => {
    void reload()
    // today меняется только при смене даты, перезагрузка по нему не нужна
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (items === null) {
    return <p className="hint">{error ?? 'Загрузка…'}</p>
  }

  if (adding) {
    return (
      <ExceptionForm
        today={today}
        onDone={async () => {
          setAdding(false)
          await reload()
        }}
        onCancel={() => setAdding(false)}
      />
    )
  }

  async function remove(item: ScheduleException) {
    await deleteException(item.id)
    await reload()
  }

  return (
    <section>
      <p className="hint">Отпуск, выходные и разовые окна поверх обычной недели.</p>
      {items.length === 0 && <p className="hint">Правок пока нет.</p>}
      <ul className="list">
        {items.map((item) => (
          <li key={item.id} className="card row">
            <span>
              <span className="card-title">{dayTitle(item.day)}</span>{' '}
              {item.kind === 'closed'
                ? item.start
                  ? `не работаю ${hhmm(item.start)}–${hhmm(item.end)}`
                  : 'выходной'
                : `доп. окно ${hhmm(item.start)}–${hhmm(item.end)}`}
            </span>
            <button type="button" className="link" onClick={() => void remove(item)}>
              Удалить
            </button>
          </li>
        ))}
      </ul>
      <button type="button" onClick={() => setAdding(true)}>
        Добавить правку
      </button>
    </section>
  )
}

type FormProps = {
  today: string
  onDone: () => void
  onCancel: () => void
}

function ExceptionForm({ today, onDone, onCancel }: FormProps) {
  const [day, setDay] = useState(today)
  const [lastDay, setLastDay] = useState(today)
  const [kind, setKind] = useState<ExceptionKind>('closed')
  const [wholeDay, setWholeDay] = useState(true)
  const [start, setStart] = useState('10:00')
  const [end, setEnd] = useState('14:00')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const withTime = kind === 'extra' || !wholeDay

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (withTime && start >= end) {
      setError('Начало должно быть раньше конца')
      return
    }
    // Отпуск задаётся диапазоном дат: по правке на каждый день
    const days: string[] = []
    for (let current = day; current <= (kind === 'closed' ? lastDay : day); current = addDays(current, 1)) {
      days.push(current)
    }
    if (days.length === 0 || days.length > 60) {
      setError('Проверьте даты: не больше 60 дней за раз')
      return
    }
    setSaving(true)
    setError(null)
    try {
      for (const current of days) {
        await createException({
          day: current,
          kind,
          start: withTime ? start : null,
          end: withTime ? end : null,
        })
      }
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setSaving(false)
    }
  }

  return (
    <form className="form" onSubmit={submit}>
      <h2>Правка расписания</h2>
      <label>
        Что сделать
        <select value={kind} onChange={(event) => setKind(event.target.value as ExceptionKind)}>
          <option value="closed">Не работаю</option>
          <option value="extra">Добавить разовое окно</option>
        </select>
      </label>
      <div className="row">
        <label>
          {kind === 'closed' ? 'С даты' : 'Дата'}
          <input
            type="date"
            value={day}
            min={today}
            onChange={(event) => {
              setDay(event.target.value)
              if (lastDay < event.target.value) setLastDay(event.target.value)
            }}
            required
          />
        </label>
        {kind === 'closed' && (
          <label>
            По дату
            <input
              type="date"
              value={lastDay}
              min={day}
              onChange={(event) => setLastDay(event.target.value)}
              required
            />
          </label>
        )}
      </div>
      {kind === 'closed' && (
        <label className="checkbox">
          <input
            type="checkbox"
            checked={wholeDay}
            onChange={(event) => setWholeDay(event.target.checked)}
          />
          Весь день
        </label>
      )}
      {withTime && (
        <div className="row">
          <label>
            С
            <input type="time" value={start} onChange={(event) => setStart(event.target.value)} required />
          </label>
          <label>
            До
            <input type="time" value={end} onChange={(event) => setEnd(event.target.value)} required />
          </label>
        </div>
      )}
      {error && <p className="error">{error}</p>}
      <div className="actions">
        <button type="submit" disabled={saving}>
          Сохранить
        </button>
        <button type="button" className="secondary" onClick={onCancel}>
          Отмена
        </button>
      </div>
    </form>
  )
}
