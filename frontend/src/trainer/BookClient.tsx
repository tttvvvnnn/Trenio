import { useEffect, useState } from 'react'

import {
  errorText,
  createTrainerBooking,
  fetchClients,
  type Booking,
  type Client,
  type Slot,
} from '../api'
import { dateTime, fullName } from '../format'
import { haptic } from '../telegram'
import Icon from '../ui/icons'
import { PersonAvatar } from '../ui/Avatar'
import { EmptyState, ErrorText, Row, Section, SkeletonList } from '../ui/kit'
import { MainButton } from '../ui/native'
import Screen from '../ui/Screen'

type Props = {
  slot: Slot
  serviceName: string
  timezone: string
  onBack: () => void
  onBooked: (booking: Booking) => void
}

/** Тренер сам записывает своего клиента в свободное окошко. */
export default function BookClient({ slot, serviceName, timezone, onBack, onBooked }: Props) {
  const [clients, setClients] = useState<Client[] | null>(null)
  const [clientId, setClientId] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchClients()
      .then(setClients)
      .catch((err: unknown) => setError(errorText(err)))
  }, [])

  async function book() {
    if (clientId === null || saving) return
    setSaving(true)
    setError(null)
    try {
      const booking = await createTrainerBooking({
        client_id: clientId,
        service_id: slot.service_id,
        starts_at: slot.starts_at,
      })
      haptic.success()
      onBooked(booking)
    } catch (err) {
      haptic.error()
      setError(errorText(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Screen
      title="Записать клиента"
      subtitle={`${serviceName} · ${dateTime(slot.starts_at, timezone)}`}
      onBack={onBack}
    >
      {clients === null && !error && <SkeletonList rows={2} />}
      {clients !== null && clients.length === 0 && (
        <EmptyState
          icon="user"
          title="Пока нет клиентов"
          text="Клиент появится, когда откроет вашу ссылку. Она во вкладке «Клиенты»."
        />
      )}
      {clients !== null && clients.length > 0 && (
        <Section footer="Запись сразу подтверждена, клиент увидит её в приложении.">
          {clients.map((client) => (
            <Row
              key={client.id}
              title={fullName(client)}
              leading={<PersonAvatar person={client} />}
              subtitle={client.username ? `@${client.username}` : undefined}
              onClick={() => {
                haptic.select()
                setClientId(client.id)
              }}
              badge={
                client.id === clientId ? <Icon name="check" className="row-check" /> : undefined
              }
            />
          ))}
        </Section>
      )}
      {error && <ErrorText>{error}</ErrorText>}
      <MainButton
        text="Записать"
        onClick={() => void book()}
        visible={clientId !== null}
        loading={saving}
      />
    </Screen>
  )
}
