import { useState } from 'react'

import { errorText, addMeasurement, type MeasurementKind, type ProgressSeries } from '../api'
import { localDate } from '../format'
import { haptic } from '../telegram'
import { Chips, ErrorText, InlineField, Section, TextField } from '../ui/kit'
import { MainButton } from '../ui/native'
import Screen from '../ui/Screen'

type Props = {
  clientId: number
  clientName: string
  timezone: string
  // Свои виды, которые уже есть у клиента: их удобно выбрать повторно
  series: ProgressSeries[]
  onBack: () => void
  onSaved: (series: ProgressSeries[]) => void
}

const KINDS: [MeasurementKind, string][] = [
  ['weight', 'Вес, кг'],
  ['waist', 'Талия, см'],
  ['chest', 'Грудь, см'],
  ['hips', 'Бёдра, см'],
  ['custom', 'Своё'],
]

// "77,4" и "77.4" — одно и то же
function parseValue(raw: string): number | null {
  const value = Number(raw.replace(',', '.').trim())
  return raw.trim() !== '' && Number.isFinite(value) && value > 0 && value < 100000 ? value : null
}

/** Новый замер. Тот же вид в тот же день заменит прежнее значение. */
export default function MeasurementForm({
  clientId,
  clientName,
  timezone,
  series,
  onBack,
  onSaved,
}: Props) {
  const [kind, setKind] = useState<MeasurementKind>('weight')
  const [day, setDay] = useState(localDate(new Date(), timezone))
  const [value, setValue] = useState('')
  const [label, setLabel] = useState('')
  const [unit, setUnit] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const custom = series.filter((item) => item.kind === 'custom')
  const number = parseValue(value)
  const valid = number !== null && day !== '' && (kind !== 'custom' || label.trim() !== '')

  async function save() {
    if (!valid || saving || number === null) return
    setSaving(true)
    setError(null)
    try {
      const saved = await addMeasurement(clientId, {
        day,
        kind,
        value: number,
        ...(kind === 'custom' ? { label: label.trim(), unit: unit.trim() } : {}),
      })
      haptic.success()
      onSaved(saved)
    } catch (err) {
      haptic.error()
      setError(errorText(err))
      setSaving(false)
    }
  }

  return (
    <Screen title="Новый замер" subtitle={clientName} onBack={onBack}>
      <section className="section">
        <h2 className="section-title">Что измеряли</h2>
        <Chips label="Что измеряли" value={kind} options={KINDS} onChange={setKind} />
      </section>
      {kind === 'custom' && (
        <>
          {custom.length > 0 && (
            <section className="section">
              <h2 className="section-title">Уже есть у клиента</h2>
              <Chips
                label="Свой вид"
                value={label.trim().toLowerCase()}
                options={custom.map((item) => [item.label.toLowerCase(), item.label])}
                onChange={(picked) => {
                  const found = custom.find((item) => item.label.toLowerCase() === picked)
                  setLabel(found?.label ?? picked)
                  setUnit(found?.unit ?? '')
                }}
              />
            </section>
          )}
          <TextField
            label="Название"
            value={label}
            onChange={setLabel}
            placeholder="Например, планка или пульс в покое"
            maxLength={48}
          />
          <TextField
            label="Единица"
            value={unit}
            onChange={setUnit}
            placeholder="сек, раз, уд/мин"
            maxLength={16}
          />
        </>
      )}
      <Section footer="Если в этот день уже был такой замер, значение заменится.">
        <InlineField label="Значение" icon={{ name: 'chart', color: 'var(--c-accent)' }}>
          {(id) => (
            <input
              id={id}
              className="row-input"
              inputMode="decimal"
              placeholder="0"
              value={value}
              onChange={(event) => setValue(event.target.value)}
            />
          )}
        </InlineField>
        <InlineField label="Дата" icon={{ name: 'calendar', color: 'var(--c-success)' }}>
          {(id) => (
            <input
              id={id}
              className="row-input"
              type="date"
              value={day}
              max={localDate(new Date(), timezone)}
              onChange={(event) => setDay(event.target.value)}
            />
          )}
        </InlineField>
      </Section>
      {error && <ErrorText>{error}</ErrorText>}
      <MainButton text="Сохранить" onClick={() => void save()} disabled={!valid} loading={saving} />
    </Screen>
  )
}
