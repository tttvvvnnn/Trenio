import { useEffect, useState } from 'react'

import {
  createPackage,
  fetchPackageTemplates,
  fetchServices,
  type Package,
  type PackageTemplate,
  type Service,
} from '../api'
import { addDays, localDate, rubles } from '../format'
import { haptic } from '../telegram'
import { Chips, ErrorText, InlineField, Section, SkeletonList, TextField } from '../ui/kit'
import { MainButton } from '../ui/native'
import Screen from '../ui/Screen'

type Props = {
  clientId: number
  clientName: string
  timezone: string
  onBack: () => void
  onSold: (pkg: Package) => void
}

const CUSTOM = 0
const ANY_SERVICE = 0

/** Тренер продаёт клиенту блок: из шаблона или со своими условиями. */
export default function SellPackage({ clientId, clientName, timezone, onBack, onSold }: Props) {
  const today = localDate(new Date(), timezone)
  const [templates, setTemplates] = useState<PackageTemplate[] | null>(null)
  const [services, setServices] = useState<Service[]>([])
  const [template, setTemplate] = useState(CUSTOM)
  const [name, setName] = useState('')
  const [serviceId, setServiceId] = useState(ANY_SERVICE)
  const [count, setCount] = useState('10')
  const [price, setPrice] = useState('')
  const [purchasedOn, setPurchasedOn] = useState(today)
  const [validUntil, setValidUntil] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([fetchPackageTemplates(), fetchServices()])
      .then(([loadedTemplates, loadedServices]) => {
        setTemplates(loadedTemplates)
        setServices(loadedServices)
        if (loadedTemplates.length > 0) apply(loadedTemplates[0], today)
      })
      .catch((err: unknown) => setError(String(err)))
    // Шаблоны грузим один раз при открытии
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function apply(chosen: PackageTemplate, purchased: string) {
    setTemplate(chosen.id)
    setName(chosen.name)
    setServiceId(chosen.service?.id ?? ANY_SERVICE)
    setCount(String(chosen.sessions_count))
    setPrice(String(chosen.price))
    setValidUntil(chosen.valid_days ? addDays(purchased, chosen.valid_days - 1) : '')
  }

  function pickTemplate(id: number) {
    const chosen = templates?.find((item) => item.id === id)
    if (chosen) apply(chosen, purchasedOn)
    else setTemplate(CUSTOM)
  }

  const sessions = Number(count)
  const amount = Number(price.replace(/\s/g, ''))
  const valid =
    name.trim() !== '' &&
    sessions >= 1 &&
    sessions <= 200 &&
    price.trim() !== '' &&
    purchasedOn !== '' &&
    (validUntil === '' || validUntil >= purchasedOn)

  async function submit() {
    if (!valid || saving) return
    setSaving(true)
    setError(null)
    try {
      const pkg = await createPackage(clientId, {
        name: name.trim(),
        service_id: serviceId === ANY_SERVICE ? null : serviceId,
        sessions_count: sessions,
        price: amount,
        purchased_on: purchasedOn,
        valid_until: validUntil || null,
      })
      haptic.success()
      onSold(pkg)
    } catch (err) {
      haptic.error()
      setError(err instanceof Error ? err.message : String(err))
      setSaving(false)
    }
  }

  return (
    <Screen title="Новый блок" subtitle={clientName} onBack={onBack}>
      {templates === null && !error && <SkeletonList rows={2} />}
      {templates !== null && (
        <>
          {templates.length > 0 && (
            <Section title="Шаблон" footer="Шаблоны настраиваются во вкладке «Услуги».">
              <Chips
                label="Шаблон"
                value={template}
                options={[
                  ...templates.map((item) => [item.id, item.name] as const),
                  [CUSTOM, 'Свой'],
                ]}
                onChange={pickTemplate}
              />
            </Section>
          )}
          <TextField
            label="Название"
            value={name}
            onChange={setName}
            placeholder="10 персональных"
            maxLength={128}
            required
          />
          <Section
            title="Услуга"
            footer="Из блока списываются занятия только этой услуги или любой, если так выбрано."
          >
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
          <Section
            title="Условия"
            footer={
              sessions > 0 && amount > 0
                ? `${rubles(Math.round(amount / sessions))} за занятие.`
                : undefined
            }
          >
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
            <InlineField label="Куплен">
              {(id) => (
                <input
                  id={id}
                  className="row-input"
                  type="date"
                  value={purchasedOn}
                  onChange={(event) => setPurchasedOn(event.target.value)}
                />
              )}
            </InlineField>
            <InlineField label="Действует до">
              {(id) => (
                <input
                  id={id}
                  className="row-input"
                  type="date"
                  min={purchasedOn}
                  value={validUntil}
                  onChange={(event) => setValidUntil(event.target.value)}
                />
              )}
            </InlineField>
          </Section>
          <p className="section-footer">
            Срок можно не указывать. Деньги внесите в карточке блока после продажи.
          </p>
        </>
      )}
      {error && <ErrorText>{error}</ErrorText>}
      <MainButton
        text="Продать блок"
        onClick={() => void submit()}
        disabled={!valid}
        loading={saving}
      />
    </Screen>
  )
}
