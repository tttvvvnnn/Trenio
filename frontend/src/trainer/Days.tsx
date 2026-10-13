import { useEffect, useState } from 'react'

import {
  createException,
  deleteException,
  fetchExceptions,
  type ExceptionKind,
  type ScheduleException,
} from '../api'
import { addDays, dateRange, dayTitle, hhmm, localDate, monthTitle, plural } from '../format'
import { confirmAction, haptic } from '../telegram'
import {
  AddRow,
  ErrorText,
  InlineField,
  Row,
  Section,
  Segmented,
  SkeletonList,
  SwitchRow,
} from '../ui/kit'
import { MainButton } from '../ui/native'
import Screen from '../ui/Screen'

// Сколько дней вперёд показываем исключения
const HORIZON_DAYS = 90

type Props = {
  timezone: string
}

// Подряд идущие выходные дни показываем одной строкой: так отпуск — одна запись, а не семь
type Group = {
  ids: number[]
  first: string
  last: string
  kind: ExceptionKind
  start: string | null
  end: string | null
}

function groupExceptions(items: ScheduleException[]): Group[] {
  const groups: Group[] = []
  for (const item of [...items].sort((a, b) => a.day.localeCompare(b.day))) {
    const previous = groups[groups.length - 1]
    const wholeDayOff = item.kind === 'closed' && item.start === null
    if (
      wholeDayOff &&
      previous?.kind === 'closed' &&
      previous.start === null &&
      addDays(previous.last, 1) === item.day
    ) {
      previous.ids.push(item.id)
      previous.last = item.day
    } else {
      groups.push({
        ids: [item.id],
        first: item.day,
        last: item.day,
        kind: item.kind,
        start: item.start,
        end: item.end,
      })
    }
  }
  return groups
}

function describe(group: Group): { title: string; subtitle: string } {
  const title = dateRange(group.first, group.last)
  if (group.kind === 'extra') {
    return { title, subtitle: `Доп. окно ${hhmm(group.start)}–${hhmm(group.end)}` }
  }
  if (group.start !== null) {
    return { title, subtitle: `Не работаю ${hhmm(group.start)}–${hhmm(group.end)}` }
  }
  const days = group.ids.length
  return {
    title,
    subtitle: days === 1 ? 'Выходной' : `Не работаю · ${plural(days, 'день', 'дня', 'дней')}`,
  }
}

function groupIcon(group: Group) {
  if (group.kind === 'extra') return { name: 'dayExtra', color: 'var(--c-success)' } as const
  if (group.start !== null) return { name: 'dayOff', color: 'var(--c-warning)' } as const
  return { name: 'dayOff', color: 'var(--c-destructive)' } as const
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

  async function remove(group: Group) {
    const { title, subtitle } = describe(group)
    const ok = await confirmAction(
      `Удалить исключение «${title}: ${subtitle.toLowerCase()}»?`,
      'Удалить',
    )
    if (!ok) return
    try {
      for (const id of group.ids) {
        await deleteException(id)
      }
      haptic.success()
    } catch (err) {
      haptic.error()
      setError(err instanceof Error ? err.message : String(err))
    }
    await reload()
  }

  if (items === null) {
    return error ? <ErrorText>{error}</ErrorText> : <SkeletonList />
  }

  const byMonth = new Map<string, Group[]>()
  for (const group of groupExceptions(items)) {
    const month = monthTitle(group.first)
    byMonth.set(month, [...(byMonth.get(month) ?? []), group])
  }

  return (
    <>
      {error && <ErrorText>{error}</ErrorText>}
      {[...byMonth.entries()].map(([month, groups]) => (
        <Section key={month} title={month}>
          {groups.map((group) => {
            const { title, subtitle } = describe(group)
            return (
              <Row
                key={group.ids[0]}
                title={title}
                subtitle={subtitle}
                icon={groupIcon(group)}
                onClick={() => void remove(group)}
              />
            )
          })}
        </Section>
      ))}
      <Section
        footer={
          items.length === 0
            ? 'Отпуск, выходной или разовое окно поверх обычной недели.'
            : 'Нажмите на исключение, чтобы удалить его.'
        }
      >
        <AddRow title="Добавить исключение" onClick={() => setAdding(true)} />
      </Section>
      {adding && (
        <ExceptionForm
          today={today}
          onDone={async () => {
            setAdding(false)
            await reload()
          }}
          onCancel={() => setAdding(false)}
        />
      )}
    </>
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
  const finalDay = kind === 'closed' ? lastDay : day
  // Отпуск задаётся диапазоном дат: по исключению на каждый день
  const days: string[] = []
  for (let current = day; current <= finalDay && days.length <= 60; current = addDays(current, 1)) {
    days.push(current)
  }
  const problem =
    withTime && start >= end
      ? 'Начало должно быть раньше конца.'
      : days.length === 0
        ? 'Последний день раньше первого.'
        : days.length > 60
          ? 'Не больше 60 дней за раз.'
          : null

  async function submit() {
    if (problem || saving) return
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
      haptic.success()
      onDone()
    } catch (err) {
      haptic.error()
      setError(err instanceof Error ? err.message : String(err))
      setSaving(false)
    }
  }

  return (
    <Screen title="Новое исключение" onBack={onCancel}>
      <form
        onSubmit={(event) => {
          event.preventDefault()
          void submit()
        }}
      >
        <Segmented
          label="Что сделать"
          value={kind}
          options={[
            ['closed', 'Не работаю'],
            ['extra', 'Доп. окно'],
          ]}
          onChange={setKind}
        />
        <Section
          title={kind === 'closed' ? 'Даты' : 'Дата'}
          footer={
            kind === 'closed' && days.length > 1 && days.length <= 60
              ? `${plural(days.length, 'день', 'дня', 'дней')}: ${dateRange(day, lastDay)}`
              : dayTitle(day)
          }
        >
          <InlineField label={kind === 'closed' ? 'С' : 'День'}>
            {(id) => (
              <input
                id={id}
                className="row-input"
                type="date"
                value={day}
                min={today}
                onChange={(event) => {
                  setDay(event.target.value)
                  if (lastDay < event.target.value) setLastDay(event.target.value)
                }}
                required
              />
            )}
          </InlineField>
          {kind === 'closed' && (
            <InlineField label="По">
              {(id) => (
                <input
                  id={id}
                  className="row-input"
                  type="date"
                  value={lastDay}
                  min={day}
                  onChange={(event) => setLastDay(event.target.value)}
                  required
                />
              )}
            </InlineField>
          )}
        </Section>
        <Section title="Время">
          {kind === 'closed' && (
            <SwitchRow label="Весь день" checked={wholeDay} onChange={setWholeDay} />
          )}
          {withTime && (
            <>
              <InlineField label="Начало">
                {(id) => (
                  <input
                    id={id}
                    className="row-input"
                    type="time"
                    value={start}
                    onChange={(event) => setStart(event.target.value)}
                    required
                  />
                )}
              </InlineField>
              <InlineField label="Конец">
                {(id) => (
                  <input
                    id={id}
                    className="row-input"
                    type="time"
                    value={end}
                    onChange={(event) => setEnd(event.target.value)}
                    required
                  />
                )}
              </InlineField>
            </>
          )}
        </Section>
        {problem && <ErrorText>{problem}</ErrorText>}
        {error && <ErrorText>{error}</ErrorText>}
        <MainButton
          text="Сохранить"
          onClick={() => void submit()}
          disabled={problem !== null}
          loading={saving}
        />
      </form>
    </Screen>
  )
}
