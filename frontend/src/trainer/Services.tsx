import { useEffect, useState } from 'react'

import { createService, fetchServices, updateService, type Service } from '../api'
import { duration, rubles } from '../format'
import { haptic } from '../telegram'
import {
  AddRow,
  Chips,
  ErrorText,
  InlineField,
  PageHeader,
  Row,
  Section,
  SkeletonList,
  Stepper,
  Switch,
  TextField,
} from '../ui/kit'
import { MainButton } from '../ui/native'
import Screen from '../ui/Screen'
import PackageTemplates from './PackageTemplates'

type Props = {
  // Внутри экрана Профиля: заголовок уже есть у экрана
  embedded?: boolean
}

export default function Services({ embedded = false }: Props) {
  const [services, setServices] = useState<Service[] | null>(null)
  // null — форма закрыта, 'new' — новая услуга, иначе редактируем эту
  const [editing, setEditing] = useState<Service | 'new' | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function reload() {
    try {
      setServices(await fetchServices(true))
    } catch (err) {
      setError(String(err))
    }
  }

  useEffect(() => {
    void reload()
  }, [])

  async function toggle(service: Service, isActive: boolean) {
    // Переключатель реагирует сразу, не дожидаясь ответа сервера
    setServices(
      (current) =>
        current?.map((item) =>
          item.id === service.id ? { ...item, is_active: isActive } : item,
        ) ?? null,
    )
    try {
      await updateService(service.id, { is_active: isActive })
    } catch (err) {
      haptic.error()
      setError(err instanceof Error ? err.message : String(err))
      await reload()
    }
  }

  return (
    <>
      {!embedded && <PageHeader title="Услуги" subtitle="На них клиенты записываются в окошки." />}
      {services === null && !error && <SkeletonList />}
      {error && <ErrorText>{error}</ErrorText>}
      {services !== null && (
        <>
          {services.length > 0 && (
            <Section footer="Выключенная услуга пропадает из окошек, но остаётся в списке.">
              {services.map((service) => (
                <Row
                  key={service.id}
                  title={service.name}
                  subtitle={serviceSummary(service)}
                  tone={service.is_active ? undefined : 'muted'}
                  onClick={() => setEditing(service)}
                  after={
                    <Switch
                      label={`Услуга «${service.name}» включена`}
                      checked={service.is_active}
                      onChange={(checked) => void toggle(service, checked)}
                    />
                  }
                />
              ))}
            </Section>
          )}
          <Section
            footer={
              services.length === 0
                ? 'Например, «Персональная, 60 минут» или «Групповая, до 8 человек».'
                : undefined
            }
          >
            <AddRow title="Добавить услугу" onClick={() => setEditing('new')} />
          </Section>
          <PackageTemplates services={services.filter((service) => service.is_active)} />
        </>
      )}
      {editing !== null && (
        <ServiceForm
          service={editing === 'new' ? null : editing}
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

function serviceSummary(service: Service): string {
  return [
    duration(service.duration_min),
    service.capacity > 1 ? `до ${service.capacity} человек` : 'индивидуально',
    service.price !== null ? rubles(service.price) : null,
    service.address,
    service.is_active ? null : 'выключена',
  ]
    .filter(Boolean)
    .join(' · ')
}

const DURATIONS = [30, 45, 60, 90, 120]
const CUSTOM = 0
const CAPACITIES = Array.from({ length: 100 }, (_, index) => index + 1)

type FormProps = {
  service: Service | null
  onDone: () => void
  onCancel: () => void
}

function ServiceForm({ service, onDone, onCancel }: FormProps) {
  const initialDuration = service?.duration_min ?? 60
  const [name, setName] = useState(service?.name ?? '')
  const [preset, setPreset] = useState(
    DURATIONS.includes(initialDuration) ? initialDuration : CUSTOM,
  )
  const [customDuration, setCustomDuration] = useState(String(initialDuration))
  const [capacity, setCapacity] = useState(service?.capacity ?? 1)
  const [price, setPrice] = useState(service?.price != null ? String(service.price) : '')
  const [address, setAddress] = useState(service?.address ?? '')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const durationMin = preset === CUSTOM ? Number(customDuration) : preset
  const valid = name.trim() !== '' && durationMin >= 5 && durationMin <= 600

  async function submit() {
    if (!valid || saving) return
    setSaving(true)
    setError(null)
    const data = {
      name: name.trim(),
      duration_min: durationMin,
      capacity,
      price: price.trim() === '' ? null : Number(price.replace(/\s/g, '')),
      address: address.trim() || null,
    }
    try {
      if (service === null) {
        await createService(data)
      } else {
        // Пустая строка очищает адрес услуги, тогда берётся адрес тренера
        await updateService(service.id, { ...data, address: data.address ?? '' })
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
    <Screen title={service === null ? 'Новая услуга' : service.name} onBack={onCancel}>
      <form
        onSubmit={(event) => {
          event.preventDefault()
          void submit()
        }}
      >
        <TextField
          label="Название"
          value={name}
          onChange={setName}
          placeholder="Персональная тренировка"
          maxLength={128}
          required
        />
        <Section
          title="Длительность"
          footer={
            durationMin > 0 && durationMin % 5 === 0
              ? `Окошки идут подряд с шагом ${duration(durationMin)}.`
              : 'Длительность от 5 до 600 минут, кратно 5.'
          }
        >
          <Chips
            label="Длительность"
            value={preset}
            options={[
              ...DURATIONS.map((value) => [value, duration(value)] as const),
              [CUSTOM, 'Другая'],
            ]}
            onChange={setPreset}
          />
          {preset === CUSTOM && (
            <InlineField label="Минут">
              {(id) => (
                <input
                  id={id}
                  className="row-input"
                  type="number"
                  inputMode="numeric"
                  min={5}
                  max={600}
                  step={5}
                  value={customDuration}
                  onChange={(event) => setCustomDuration(event.target.value)}
                />
              )}
            </InlineField>
          )}
        </Section>
        <Section title="Детали">
          <Row
            title="Человек за раз"
            after={
              <Stepper
                label="Человек за раз"
                value={capacity}
                options={CAPACITIES}
                onChange={setCapacity}
              />
            }
          />
          <InlineField label="Цена, ₽">
            {(id) => (
              <input
                id={id}
                className="row-input"
                inputMode="numeric"
                placeholder="не указана"
                value={price}
                onChange={(event) => setPrice(event.target.value.replace(/[^\d\s]/g, ''))}
              />
            )}
          </InlineField>
          <InlineField label="Место">
            {(id) => (
              <input
                id={id}
                className="row-input"
                placeholder="как в профиле"
                maxLength={256}
                value={address}
                onChange={(event) => setAddress(event.target.value)}
              />
            )}
          </InlineField>
        </Section>
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
