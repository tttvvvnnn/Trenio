import { useEffect, useState, type FormEvent } from 'react'

import {
  createRule,
  deleteRule,
  fetchRules,
  fetchServices,
  replaceRule,
  type Rule,
  type Service,
} from '../api'
import { hhmm, WEEKDAYS } from '../format'

export default function WeekTemplate() {
  const [rules, setRules] = useState<Rule[] | null>(null)
  const [services, setServices] = useState<Service[]>([])
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
    return <p className="hint">{error ?? 'Загрузка…'}</p>
  }

  if (editing !== null) {
    return (
      <RuleForm
        rule={editing === 'new' ? null : editing}
        services={services}
        onDone={async () => {
          setEditing(null)
          await reload()
        }}
        onCancel={() => setEditing(null)}
      />
    )
  }

  function serviceNames(rule: Rule): string {
    if (rule.service_ids.length === 0) return 'все услуги'
    return services
      .filter((service) => rule.service_ids.includes(service.id))
      .map((service) => service.name)
      .join(', ')
  }

  async function remove(rule: Rule) {
    await deleteRule(rule.id)
    await reload()
  }

  return (
    <section>
      <p className="hint">
        Рабочие часы на обычной неделе. Отпуск и разовые изменения задаются во вкладке «Дни».
      </p>
      {WEEKDAYS.map((title, weekday) => {
        const dayRules = rules.filter((rule) => rule.weekday === weekday)
        return (
          <div key={weekday} className="card">
            <div className="card-title">{title}</div>
            {dayRules.length === 0 && <div className="hint">выходной</div>}
            {dayRules.map((rule) => (
              <div key={rule.id} className="row">
                <span>
                  {hhmm(rule.start)}–{hhmm(rule.end)}{' '}
                  <span className="hint">{serviceNames(rule)}</span>
                </span>
                <span className="actions">
                  <button type="button" className="link" onClick={() => setEditing(rule)}>
                    Изменить
                  </button>
                  <button type="button" className="link" onClick={() => void remove(rule)}>
                    Удалить
                  </button>
                </span>
              </div>
            ))}
          </div>
        )
      })}
      <button type="button" onClick={() => setEditing('new')}>
        Добавить рабочие часы
      </button>
    </section>
  )
}

type FormProps = {
  rule: Rule | null
  services: Service[]
  onDone: () => void
  onCancel: () => void
}

function RuleForm({ rule, services, onDone, onCancel }: FormProps) {
  const [weekday, setWeekday] = useState(rule?.weekday ?? 0)
  const [start, setStart] = useState(hhmm(rule?.start ?? '10:00'))
  const [end, setEnd] = useState(hhmm(rule?.end ?? '14:00'))
  const [serviceIds, setServiceIds] = useState<number[]>(rule?.service_ids ?? [])
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  function toggleService(id: number) {
    setServiceIds((current) =>
      current.includes(id) ? current.filter((value) => value !== id) : [...current, id],
    )
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (start >= end) {
      setError('Начало должно быть раньше конца')
      return
    }
    setSaving(true)
    setError(null)
    const data = { weekday, start, end, service_ids: serviceIds }
    try {
      if (rule === null) {
        await createRule(data)
      } else {
        await replaceRule(rule.id, data)
      }
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setSaving(false)
    }
  }

  return (
    <form className="form" onSubmit={submit}>
      <h2>Рабочие часы</h2>
      <label>
        День недели
        <select value={weekday} onChange={(event) => setWeekday(Number(event.target.value))}>
          {WEEKDAYS.map((title, index) => (
            <option key={index} value={index}>
              {title}
            </option>
          ))}
        </select>
      </label>
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
      {services.length > 0 && (
        <fieldset>
          <legend>Услуги в эти часы (ничего не выбрано — все)</legend>
          {services.map((service) => (
            <label key={service.id} className="checkbox">
              <input
                type="checkbox"
                checked={serviceIds.includes(service.id)}
                onChange={() => toggleService(service.id)}
              />
              {service.name}
            </label>
          ))}
        </fieldset>
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
