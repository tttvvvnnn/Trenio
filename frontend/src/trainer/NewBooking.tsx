import { useEffect, useState } from 'react'

import {
  createTrainerBooking,
  fetchClients,
  fetchServices,
  fetchSlots,
  type Booking,
  type Client,
  type Service,
} from '../api'
import { dateTime, duration, fullName } from '../format'
import { haptic } from '../telegram'
import Icon from '../ui/icons'
import { PersonAvatar } from '../ui/Avatar'
import { Chips, EmptyState, ErrorText, Row, Section, SkeletonList } from '../ui/kit'
import { MainButton } from '../ui/native'
import Screen from '../ui/Screen'
import SlotPicker from '../ui/SlotPicker'

type Props = {
  timezone: string
  // Из карточки клиента клиент уже известен
  client?: Client
  // Из календаря: с какого дня открыть
  day?: string
  onBack: () => void
  onBooked: (booking: Booking) => void
}

/** Тренер записывает клиента: в свободное окошко или на любое своё время. */
export default function NewBooking({ timezone, client, day, onBack, onBooked }: Props) {
  const [services, setServices] = useState<Service[] | null>(null)
  const [serviceId, setServiceId] = useState<number | null>(null)
  const [clients, setClients] = useState<Client[] | null>(client ? [client] : null)
  const [clientId, setClientId] = useState<number | null>(client?.id ?? null)
  const [startsAt, setStartsAt] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reloads, setReloads] = useState(0)

  useEffect(() => {
    fetchServices()
      .then((loaded) => {
        setServices(loaded)
        setServiceId(loaded[0]?.id ?? null)
      })
      .catch((err: unknown) => setError(String(err)))
    if (!client) {
      fetchClients()
        .then(setClients)
        .catch((err: unknown) => setError(String(err)))
    }
  }, [client])

  async function book() {
    if (clientId === null || serviceId === null || startsAt === null || saving) return
    setSaving(true)
    setError(null)
    try {
      const booking = await createTrainerBooking({
        client_id: clientId,
        service_id: serviceId,
        starts_at: startsAt,
      })
      haptic.success()
      onBooked(booking)
    } catch (err) {
      haptic.error()
      setError(err instanceof Error ? err.message : String(err))
      setStartsAt(null)
      setReloads((count) => count + 1)
    } finally {
      setSaving(false)
    }
  }

  const service = services?.find((item) => item.id === serviceId) ?? null
  const chosen = clients?.find((item) => item.id === clientId) ?? null

  return (
    <Screen title="Новая запись" subtitle={chosen ? fullName(chosen) : undefined} onBack={onBack}>
      {(services === null || clients === null) && !error && <SkeletonList rows={2} />}
      {services !== null && services.length === 0 && (
        <EmptyState
          icon="list"
          title="Пока нет услуг"
          text="Добавьте услугу во вкладке «Услуги», и можно будет записывать клиентов."
        />
      )}
      {clients !== null && clients.length === 0 && (
        <EmptyState
          icon="user"
          title="Пока нет клиентов"
          text="Клиент появится, когда откроет вашу ссылку. Она во вкладке «Клиенты»."
        />
      )}
      {!client && clients !== null && clients.length > 0 && (
        <Section title="Клиент">
          {clients.map((item) => (
            <Row
              key={item.id}
              title={fullName(item)}
              leading={<PersonAvatar person={item} />}
              subtitle={item.username ? `@${item.username}` : undefined}
              onClick={() => {
                haptic.select()
                setClientId(item.id)
              }}
              badge={item.id === clientId ? <Icon name="check" className="row-check" /> : undefined}
            />
          ))}
        </Section>
      )}
      {services !== null && service && clients !== null && clients.length > 0 && (
        <>
          {services.length > 1 && (
            <section className="section">
              <h2 className="section-title">Услуга</h2>
              <Chips
                label="Услуга"
                value={service.id}
                options={services.map((item) => [item.id, item.name] as const)}
                onChange={(id) => {
                  setStartsAt(null)
                  setServiceId(id)
                }}
              />
            </section>
          )}
          <p className="section-footer">
            {service.name} · {duration(service.duration_min)}
          </p>
          <SlotPicker
            timezone={timezone}
            capacity={service.capacity}
            load={(from, count) => fetchSlots(count, from, service.id)}
            reloadKey={`${service.id}:${reloads}`}
            value={startsAt}
            onChange={setStartsAt}
            allowCustom
            initialDay={day}
          />
          <p className="section-footer">Запись сразу подтверждена, клиенту придёт уведомление.</p>
        </>
      )}
      {error && <ErrorText>{error}</ErrorText>}
      <MainButton
        text={startsAt ? `Записать: ${dateTime(startsAt, timezone)}` : 'Записать'}
        onClick={() => void book()}
        visible={clientId !== null && startsAt !== null}
        loading={saving}
      />
    </Screen>
  )
}
