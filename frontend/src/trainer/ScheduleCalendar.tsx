import { useEffect, useState } from 'react'

import {
  copyWeek,
  fetchDayHours,
  fetchServices,
  resetDays,
  setDays,
  type DayHours,
  type Service,
  type Window,
} from '../api'
import { monthDays, shortRange } from '../calendar'
import { dayOfMonth, dayTitle, hhmm, localDate, plural, shortDate } from '../format'
import { confirmAction, haptic } from '../telegram'
import { AddRow, Chips, ErrorText, InlineField, Row, Section, SwitchRow } from '../ui/kit'
import MonthGrid from '../ui/MonthGrid'
import { MainButton } from '../ui/native'
import Screen from '../ui/Screen'

// Сколько промежутков помещается в клетку, остальные — «+N»
const WINDOWS_PER_DAY = 2

type Props = {
  timezone: string
}

/** Расписание на месяц: часы каждого дня, правка одной или нескольких дат. */
export default function ScheduleCalendar({ timezone }: Props) {
  const today = localDate(new Date(), timezone)
  const [month, setMonth] = useState(`${today.slice(0, 7)}-01`)
  const [hours, setHours] = useState<{ month: string; days: DayHours[] } | null>(null)
  const [services, setServices] = useState<Service[]>([])
  const [selected, setSelected] = useState<string[]>([today])
  const [multi, setMulti] = useState(false)
  const [form, setForm] = useState<'hours' | 'repeat' | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reloads, setReloads] = useState(0)

  useEffect(() => {
    fetchServices()
      .then(setServices)
      .catch((err: unknown) => setError(String(err)))
  }, [])

  useEffect(() => {
    const days = monthDays(month)
    fetchDayHours(days[0], days.length)
      .then((loaded) => setHours({ month, days: loaded }))
      .catch((err: unknown) => setError(String(err)))
  }, [month, reloads])

  const byDay = new Map((hours?.days ?? []).map((item) => [item.day, item]))
  const chosen = selected.map((day) => byDay.get(day)).filter((item) => item !== undefined)
  const first = chosen[0]

  function pick(day: string) {
    if (!multi) {
      setSelected([day])
      return
    }
    setSelected((current) =>
      current.includes(day) ? current.filter((item) => item !== day) : [...current, day].sort(),
    )
  }

  function showMonth(next: string) {
    setMonth(next)
    if (!multi) setSelected([next.slice(0, 7) === today.slice(0, 7) ? today : next])
  }

  async function run(action: () => Promise<void>) {
    setBusy(true)
    setError(null)
    try {
      await action()
      haptic.success()
      setForm(null)
      setReloads((count) => count + 1)
    } catch (err) {
      haptic.error()
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  async function dayOff() {
    if (selected.some((day) => (byDay.get(day)?.windows.length ?? 0) > 0)) {
      const ok = await confirmAction(
        'Сделать выходным? Уже созданные записи останутся, новые окошки пропадут.',
        'Выходной',
      )
      if (!ok) return
    }
    void run(() => setDays(selected, []))
  }

  const serviceNames = (window: Window) =>
    window.service_ids.length === 0
      ? 'все услуги'
      : services
          .filter((service) => window.service_ids.includes(service.id))
          .map((service) => service.name)
          .join(', ')

  const title =
    selected.length === 1
      ? dayTitle(selected[0])
      : `Выбрано ${plural(selected.length, 'день', 'дня', 'дней')}`
  const anyCustom = chosen.some((item) => item.custom)

  return (
    <>
      <MonthGrid
        month={month}
        today={today}
        isSelected={(day) => selected.includes(day)}
        loading={hours?.month !== month}
        onMonth={showMonth}
        onSelect={pick}
        dayClass={(day) => {
          const item = byDay.get(day)
          if (!item) return undefined
          return [
            item.custom && 'custom',
            item.windows.length === 0 && 'off',
            day < today && 'past',
          ]
            .filter(Boolean)
            .join(' ')
        }}
        dayLabel={(day) => {
          const item = byDay.get(day)
          if (!item || item.windows.length === 0) return `${dayOfMonth(day)}, выходной`
          return `${dayOfMonth(day)}, ${item.windows.map((w) => shortRange(w.start, w.end)).join(', ')}`
        }}
        renderDay={(day) => {
          const item = byDay.get(day)
          if (!item) return null
          if (item.windows.length === 0) return <span className="month-hours off">вых.</span>
          return (
            <>
              {item.windows.slice(0, WINDOWS_PER_DAY).map((window) => (
                <span key={window.start} className="month-hours">
                  {shortRange(window.start, window.end)}
                </span>
              ))}
              {item.windows.length > WINDOWS_PER_DAY && (
                <span className="month-more">+{item.windows.length - WINDOWS_PER_DAY}</span>
              )}
            </>
          )
        }}
        legend={
          <>
            <span>
              <i className="month-dot custom-hours" />
              свои часы на дату
            </span>
            <span>
              <i className="month-dot missed" />
              по шаблону недели
            </span>
          </>
        }
      />
      <Section>
        <SwitchRow
          label="Выбрать несколько дней"
          checked={multi}
          onChange={(checked) => {
            setMulti(checked)
            if (!checked) setSelected((current) => current.slice(0, 1))
          }}
        />
      </Section>
      {selected.length === 0 ? (
        <p className="section-footer">Нажмите на дни в календаре, чтобы выбрать их.</p>
      ) : (
        <>
          <Section
            title={title}
            footer={
              selected.length === 1 && first
                ? first.custom
                  ? 'Свои часы на эту дату: шаблон недели в этот день не действует.'
                  : 'Часы из шаблона недели. Измените их, чтобы задать свои на эту дату.'
                : selected.map(shortDate).join(', ')
            }
          >
            {selected.length === 1 && first && first.windows.length === 0 && (
              <Row title="Выходной" tone="muted" />
            )}
            {selected.length === 1 &&
              first?.windows.map((window) => (
                <Row
                  key={window.start}
                  title={`${hhmm(window.start)}–${hhmm(window.end)}`}
                  subtitle={serviceNames(window)}
                />
              ))}
            <Row title="Изменить часы" tone="accent" onClick={() => setForm('hours')} />
            <Row
              title="Сделать выходным"
              tone="accent"
              onClick={busy ? undefined : () => void dayOff()}
            />
            {anyCustom && (
              <Row
                title="Вернуть как в шаблоне недели"
                tone="accent"
                onClick={busy ? undefined : () => void run(() => resetDays(selected))}
              />
            )}
          </Section>
          <Section footer="Часы недели с выбранным днём повторятся на следующие недели.">
            <Row title="Повторить эту неделю…" tone="accent" onClick={() => setForm('repeat')} />
          </Section>
        </>
      )}
      {error && <ErrorText>{error}</ErrorText>}
      {form === 'hours' && (
        <DayForm
          days={selected}
          initial={first?.windows ?? []}
          services={services}
          error={error}
          onBack={() => setForm(null)}
          onSave={(windows) => run(() => setDays(selected, windows))}
        />
      )}
      {form === 'repeat' && selected.length > 0 && (
        <RepeatWeek
          day={selected[0]}
          error={error}
          onBack={() => setForm(null)}
          onSave={(weeks) => run(() => copyWeek(selected[0], weeks))}
        />
      )}
    </>
  )
}

type DayFormProps = {
  days: string[]
  initial: Window[]
  services: Service[]
  error: string | null
  onBack: () => void
  onSave: (windows: Window[]) => Promise<void>
}

const EMPTY_WINDOW: Window = { start: '10:00', end: '14:00', service_ids: [] }

function DayForm({ days, initial, services, error, onBack, onSave }: DayFormProps) {
  const [windows, setWindows] = useState<Window[]>(
    initial.length > 0
      ? initial.map((w) => ({ ...w, start: hhmm(w.start), end: hhmm(w.end) }))
      : [EMPTY_WINDOW],
  )
  const [saving, setSaving] = useState(false)
  const valid = windows.every((w) => w.start !== '' && w.end !== '' && w.start < w.end)

  function change(index: number, patch: Partial<Window>) {
    setWindows((current) => current.map((w, i) => (i === index ? { ...w, ...patch } : w)))
  }

  function toggleService(index: number, id: number) {
    const ids = windows[index].service_ids
    change(index, {
      service_ids: ids.includes(id) ? ids.filter((item) => item !== id) : [...ids, id],
    })
  }

  async function submit() {
    if (!valid || saving) return
    setSaving(true)
    await onSave(windows)
    setSaving(false)
  }

  return (
    <Screen
      title="Часы работы"
      subtitle={days.length === 1 ? dayTitle(days[0]) : plural(days.length, 'день', 'дня', 'дней')}
      onBack={onBack}
    >
      {windows.map((window, index) => (
        <Section
          key={index}
          title={windows.length > 1 ? `Промежуток ${index + 1}` : 'Время'}
          footer={window.start >= window.end ? 'Начало должно быть раньше конца.' : undefined}
        >
          <InlineField label="Начало">
            {(id) => (
              <input
                id={id}
                className="row-input"
                type="time"
                value={window.start}
                onChange={(event) => change(index, { start: event.target.value })}
              />
            )}
          </InlineField>
          <InlineField label="Конец">
            {(id) => (
              <input
                id={id}
                className="row-input"
                type="time"
                value={window.end}
                onChange={(event) => change(index, { end: event.target.value })}
              />
            )}
          </InlineField>
          {services.length > 1 && (
            <div className="chips" role="group" aria-label="Услуги">
              <button
                type="button"
                role="checkbox"
                className="chip"
                aria-checked={window.service_ids.length === 0}
                onClick={() => change(index, { service_ids: [] })}
              >
                Все услуги
              </button>
              {services.map((service) => (
                <button
                  key={service.id}
                  type="button"
                  role="checkbox"
                  className="chip"
                  aria-checked={window.service_ids.includes(service.id)}
                  onClick={() => toggleService(index, service.id)}
                >
                  {service.name}
                </button>
              ))}
            </div>
          )}
          {windows.length > 1 && (
            <Row
              title="Убрать промежуток"
              tone="destructive"
              onClick={() => setWindows((current) => current.filter((_, i) => i !== index))}
            />
          )}
        </Section>
      ))}
      <Section footer="Например, 10–14 и 17–21 с перерывом. Часы заменят шаблон недели в эти дни.">
        <AddRow
          title="Добавить промежуток"
          onClick={() => {
            const last = windows[windows.length - 1]
            setWindows((current) => [
              ...current,
              { start: last ? last.end : '10:00', end: '21:00', service_ids: [] },
            ])
          }}
        />
      </Section>
      {error && <ErrorText>{error}</ErrorText>}
      <MainButton
        text="Сохранить"
        onClick={() => void submit()}
        disabled={!valid}
        loading={saving}
      />
    </Screen>
  )
}

type RepeatProps = {
  day: string
  error: string | null
  onBack: () => void
  onSave: (weeks: number) => Promise<void>
}

function RepeatWeek({ day, error, onBack, onSave }: RepeatProps) {
  const [weeks, setWeeks] = useState(4)
  const [saving, setSaving] = useState(false)
  return (
    <Screen title="Повторить неделю" subtitle={`неделя с ${dayTitle(day)}`} onBack={onBack}>
      <Section
        title="На сколько недель вперёд"
        footer="Дни со своими часами скопируются, дни по шаблону останутся по шаблону. Записи клиентов не меняются."
      >
        <Chips
          label="Недель"
          value={weeks}
          options={[1, 2, 3, 4, 8].map((count) => [count, String(count)] as const)}
          onChange={setWeeks}
        />
      </Section>
      {error && <ErrorText>{error}</ErrorText>}
      <MainButton
        text={`Повторить на ${plural(weeks, 'неделю', 'недели', 'недель')}`}
        onClick={() => {
          setSaving(true)
          void onSave(weeks).finally(() => setSaving(false))
        }}
        loading={saving}
      />
    </Screen>
  )
}
