import { useEffect, useState } from 'react'

import {
  createPackageTemplate,
  deletePackageTemplate,
  fetchPackageTemplates,
  replacePackageTemplate,
  type PackageTemplate,
  type Service,
} from '../api'
import { plural, rubles } from '../format'
import { confirmAction, haptic } from '../telegram'
import { AddRow, Chips, ErrorText, InlineField, Row, Section, TextField } from '../ui/kit'
import { MainButton } from '../ui/native'
import Screen from '../ui/Screen'

type Props = {
  services: Service[]
}

/** Шаблоны блоков во вкладке «Услуги»: «10 персональных за 20 000». */
export default function PackageTemplates({ services }: Props) {
  const [templates, setTemplates] = useState<PackageTemplate[] | null>(null)
  const [editing, setEditing] = useState<PackageTemplate | 'new' | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function reload() {
    try {
      setTemplates(await fetchPackageTemplates())
    } catch (err) {
      setError(String(err))
    }
  }

  useEffect(() => {
    void reload()
  }, [])

  if (templates === null) return error ? <ErrorText>{error}</ErrorText> : null

  return (
    <>
      <Section
        title="Шаблоны блоков"
        footer="Блок — несколько занятий по одной цене. Шаблон подставляет условия, когда вы продаёте блок в карточке клиента."
      >
        {templates.map((template) => (
          <Row
            key={template.id}
            title={template.name}
            subtitle={templateSummary(template)}
            chevron
            onClick={() => setEditing(template)}
          />
        ))}
        <AddRow title="Добавить шаблон" onClick={() => setEditing('new')} />
      </Section>
      {editing !== null && (
        <TemplateForm
          template={editing === 'new' ? null : editing}
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

function templateSummary(template: PackageTemplate): string {
  return [
    plural(template.sessions_count, 'занятие', 'занятия', 'занятий'),
    rubles(template.price),
    template.service?.name ?? 'любая услуга',
    template.valid_days ? `${plural(template.valid_days, 'день', 'дня', 'дней')}` : null,
  ]
    .filter(Boolean)
    .join(' · ')
}

const ANY_SERVICE = 0

type FormProps = {
  template: PackageTemplate | null
  services: Service[]
  onDone: () => void
  onCancel: () => void
}

function TemplateForm({ template, services, onDone, onCancel }: FormProps) {
  const [name, setName] = useState(template?.name ?? '')
  const [serviceId, setServiceId] = useState(template?.service?.id ?? ANY_SERVICE)
  const [count, setCount] = useState(String(template?.sessions_count ?? 10))
  const [price, setPrice] = useState(template ? String(template.price) : '')
  const [validDays, setValidDays] = useState(
    template?.valid_days ? String(template.valid_days) : '',
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const sessions = Number(count)
  const days = validDays === '' ? null : Number(validDays)
  const valid =
    name.trim() !== '' &&
    sessions >= 1 &&
    sessions <= 200 &&
    price.trim() !== '' &&
    (days === null || (days >= 1 && days <= 3650))

  async function submit() {
    if (!valid || saving) return
    setSaving(true)
    setError(null)
    const data = {
      name: name.trim(),
      service_id: serviceId === ANY_SERVICE ? null : serviceId,
      sessions_count: sessions,
      price: Number(price.replace(/\s/g, '')),
      valid_days: days,
    }
    try {
      if (template === null) await createPackageTemplate(data)
      else await replacePackageTemplate(template.id, data)
      haptic.success()
      onDone()
    } catch (err) {
      haptic.error()
      setError(err instanceof Error ? err.message : String(err))
      setSaving(false)
    }
  }

  async function remove() {
    if (template === null) return
    const ok = await confirmAction('Удалить шаблон? Уже проданные блоки не изменятся.', 'Удалить')
    if (!ok) return
    try {
      await deletePackageTemplate(template.id)
      haptic.success()
      onDone()
    } catch (err) {
      haptic.error()
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <Screen title={template === null ? 'Новый шаблон' : template.name} onBack={onCancel}>
      <TextField
        label="Название"
        value={name}
        onChange={setName}
        placeholder="10 персональных"
        maxLength={128}
        required
      />
      <Section title="Услуга">
        <Chips
          label="Услуга"
          value={serviceId}
          options={[
            [ANY_SERVICE, 'Любая'],
            ...services.map((service) => [service.id, service.name] as const),
          ]}
          onChange={setServiceId}
        />
      </Section>
      <Section title="Условия" footer="Срок считается от даты покупки. Пусто — бессрочно.">
        <InlineField label="Занятий">
          {(id) => (
            <input
              id={id}
              className="row-input"
              inputMode="numeric"
              value={count}
              onChange={(event) => setCount(event.target.value.replace(/\D/g, ''))}
            />
          )}
        </InlineField>
        <InlineField label="Цена, ₽">
          {(id) => (
            <input
              id={id}
              className="row-input"
              inputMode="numeric"
              placeholder="20 000"
              value={price}
              onChange={(event) => setPrice(event.target.value.replace(/[^\d\s]/g, ''))}
            />
          )}
        </InlineField>
        <InlineField label="Действует, дней">
          {(id) => (
            <input
              id={id}
              className="row-input"
              inputMode="numeric"
              placeholder="бессрочно"
              value={validDays}
              onChange={(event) => setValidDays(event.target.value.replace(/\D/g, ''))}
            />
          )}
        </InlineField>
      </Section>
      {template !== null && (
        <Section>
          <Row title="Удалить шаблон" tone="destructive" onClick={() => void remove()} />
        </Section>
      )}
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
