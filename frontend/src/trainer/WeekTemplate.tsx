import { useEffect, useState } from 'react'

import {
  createRule,
  deleteRule,
  fetchRules,
  fetchServices,
  replaceRule,
  type Rule,
  type Service,
} from '../api'
import { hhmm, WEEKDAYS, WEEKDAYS_SHORT } from '../format'
import { confirmAction, haptic } from '../telegram'
import Icon from '../ui/icons'
import { AddRow, ErrorText, InlineField, Row, Section, SkeletonList } from '../ui/kit'
import { MainButton } from '../ui/native'
import Screen from '../ui/Screen'

export default function WeekTemplate() {
  const [rules, setRules] = useState<Rule[] | null>(null)
  const [services, setServices] = useState<Service[]>([])
  const [openDay, setOpenDay] = useState<number | null>(null)
  const [editing, setEditing] = useState<Rule | 'new' | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function reload() {
    try {
      const [loadedRules, loadedServices] = await Promise.all([fetchRules(), fetchServices()])
      setRules(loadedRules)
      setServices(loadedServices)
    } catch (err) {
      setError(String(err))
    }
  }

  useEffect(() => {
    void reload()
  }, [])

  if (rules === null) {
    return error ? <ErrorText>{error}</ErrorText> : <SkeletonList rows={7} />
  }

  function serviceNames(rule: Rule): string {
    if (rule.service_ids.length === 0) return 'все услуги'
    return services
      .filter((service) => rule.service_ids.includes(service.id))
      .map((service) => service.name)
      .join(', ')
  }

  const rulesOf = (weekday: number) =>
    rules.filter((rule) => rule.weekday === weekday).sort((a, b) => a.start.localeCompare(b.start))

  return (
    <>
      <Section title="Рабочие часы" footer="Нажмите на день, чтобы изменить часы.">
        {WEEKDAYS.map((title, weekday) => {
          const dayRules = rulesOf(weekday)
          if (dayRules.length === 0) {
            return (
              <Row
                key={weekday}
                title={title}
                tone="muted"
                onClick={() => setOpenDay(weekday)}
                after={<span className="badge">выходной</span>}
              />
            )
          }
          const allServices = dayRules.every((rule) => rule.service_ids.length === 0)
          const hours = dayRules.map((rule) => `${hhmm(rule.start)}–${hhmm(rule.end)}`).join(', ')
          return (
            <Row
              key={weekday}
              title={title}
              subtitle={allServices ? `${hours} · все услуги` : hours}
              chevron
              onClick={() => setOpenDay(weekday)}
            />
          )
        })}
      </Section>
      {openDay !== null && (
        <Screen
          title={WEEKDAYS[openDay]}
          subtitle="Клиенты видят окошки только в эти часы."
          onBack={() => setOpenDay(null)}
        >
          {rulesOf(openDay).length > 0 && (
            <Section title="Часы">
              {rulesOf(openDay).map((rule) => (
                <Row
                  key={rule.id}
                  title={`${hhmm(rule.start)}–${hhmm(rule.end)}`}
                  subtitle={serviceNames(rule)}
                  chevron
                  onClick={() => setEditing(rule)}
                />
              ))}
            </Section>
          )}
          <Section footer={rulesOf(openDay).length === 0 ? 'Сейчас это выходной.' : undefined}>
            <AddRow title="Добавить часы" onClick={() => setEditing('new')} />
          </Section>
        </Screen>
      )}
      {editing !== null && openDay !== null && (
        <RuleForm
          rule={editing === 'new' ? null : editing}
          weekday={openDay}
          services={services}
          onDone={async () => {
            setEditing(null)
            await reload()
          }}
          onCancel={() => setEditing(null)}
        />
      )}
    </>
  )
}

type FormProps = {
  rule: Rule | null
  weekday: number
  services: Service[]
  onDone: () => void
  onCancel: () => void
}

function RuleForm({ rule, weekday, services, onDone, onCancel }: FormProps) {
  // Новые часы можно сразу добавить на несколько дней
  const [weekdays, setWeekdays] = useState<number[]>([rule?.weekday ?? weekday])
  const [start, setStart] = useState(hhmm(rule?.start ?? '10:00'))
  const [end, setEnd] = useState(hhmm(rule?.end ?? '14:00'))
  const [serviceIds, setServiceIds] = useState<number[]>(rule?.service_ids ?? [])
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const timeError = start && end && start >= end ? 'Начало должно быть раньше конца.' : null
  const valid = !timeError && start !== '' && end !== '' && weekdays.length > 0

  function toggle<T>(list: T[], value: T): T[] {
    haptic.select()
    return list.includes(value) ? list.filter((item) => item !== value) : [...list, value]
  }

  async function submit() {
    if (!valid || saving) return
    setSaving(true)
    setError(null)
    try {
      if (rule === null) {
        for (const day of weekdays) {
          await createRule({ weekday: day, start, end, service_ids: serviceIds })
        }
      } else {
        await replaceRule(rule.id, { weekday: rule.weekday, start, end, service_ids: serviceIds })
      }
      haptic.success()
      onDone()
    } catch (err) {
      haptic.error()
      setError(err instanceof Error ? err.message : String(err))
      setSaving(false)
    }
  }

  async function remove() {
    if (rule === null) return
    const ok = await confirmAction(
      `Удалить часы ${hhmm(rule.start)}–${hhmm(rule.end)} в ${WEEKDAYS[rule.weekday].toLowerCase()}?`,
      'Удалить',
    )
    if (!ok) return
    try {
      await deleteRule(rule.id)
      haptic.success()
      onDone()
    } catch (err) {
      haptic.error()
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <Screen title={rule === null ? 'Новые часы' : 'Рабочие часы'} onBack={onCancel}>
      <form
        onSubmit={(event) => {
          event.preventDefault()
          void submit()
        }}
      >
        {rule === null && (
          <Section title="Дни недели">
            <div className="chips" role="group" aria-label="Дни недели">
              {WEEKDAYS_SHORT.map((title, day) => (
                <button
                  key={day}
                  type="button"
                  role="checkbox"
                  className="chip"
                  aria-checked={weekdays.includes(day)}
                  aria-label={WEEKDAYS[day]}
                  onClick={() => setWeekdays((current) => toggle(current, day))}
                >
                  {title}
                </button>
              ))}
            </div>
          </Section>
        )}
        <Section title="Время">
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
        </Section>
        {timeError && <ErrorText>{timeError}</ErrorText>}
        {services.length > 0 && (
          <Section title="Услуги в эти часы">
            <CheckRow
              title="Все услуги"
              checked={serviceIds.length === 0}
              onClick={() => {
                haptic.select()
                setServiceIds([])
              }}
            />
            {services.map((service) => (
              <CheckRow
                key={service.id}
                title={service.name}
                checked={serviceIds.includes(service.id)}
                onClick={() => setServiceIds((current) => toggle(current, service.id))}
              />
            ))}
          </Section>
        )}
        {rule !== null && (
          <Section>
            <Row title="Удалить часы" tone="destructive" onClick={() => void remove()} />
          </Section>
        )}
        {error && <ErrorText>{error}</ErrorText>}
        <MainButton
          text="Сохранить"
          onClick={() => void submit()}
          disabled={!valid}
          loading={saving}
        />
      </form>
    </Screen>
  )
}

type CheckRowProps = {
  title: string
  checked: boolean
  onClick: () => void
}

function CheckRow({ title, checked, onClick }: CheckRowProps) {
  return (
    <div className="row">
      <button
        type="button"
        role="checkbox"
        aria-checked={checked}
        className="row-main"
        onClick={onClick}
      >
        <span className="row-text">{title}</span>
        {checked && <Icon name="check" className="row-check" />}
      </button>
    </div>
  )
}
