import { useState } from 'react'

import { changeTrainerBooking, type Booking, type BookingAction } from '../api'
import { dateTime, duration, fullName } from '../format'
import { confirmAction, haptic } from '../telegram'
import { ErrorText, Row, Section } from '../ui/kit'
import { MainButton } from '../ui/native'
import Screen from '../ui/Screen'
import StatusBadge from '../ui/StatusBadge'

type Props = {
  booking: Booking
  onBack: () => void
  onChanged: (booking: Booking) => void
}

/** Запись глазами тренера: кто, когда, и что с ней сделать. */
export default function BookingDetails({ booking, onBack, onChanged }: Props) {
  const [busy, setBusy] = useState<BookingAction | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { client } = booking
  const timezone = booking.trainer.timezone

  async function act(action: BookingAction) {
    if (action === 'cancel') {
      const ok = await confirmAction(
        'Отменить запись? Время освободится, клиент увидит отмену в приложении.',
        'Отменить',
      )
      if (!ok) return
    }
    setBusy(action)
    setError(null)
    try {
      const updated = await changeTrainerBooking(booking.id, action)
      haptic.success()
      onChanged(updated)
    } catch (err) {
      haptic.error()
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(null)
    }
  }

  const pending = booking.status === 'pending'
  let note: string | null = null
  if (pending) note = 'Клиент ждёт ответа. Пока запись не отклонена, время занято.'
  else if (booking.status === 'cancelled')
    note = booking.cancelled_by === 'client' ? 'Клиент отменил запись.' : 'Вы отменили запись.'
  else if (booking.created_by === 'trainer') note = 'Вы записали клиента сами.'

  return (
    <Screen
      title={fullName(client)}
      subtitle={client.username ? `@${client.username}` : undefined}
      onBack={onBack}
    >
      <Section footer={note}>
        <Row title="Статус" after={<StatusBadge status={booking.status} />} />
        <Row title="Когда" subtitle={dateTime(booking.starts_at, timezone)} />
        <Row
          title="Услуга"
          value={`${booking.service.name}, ${duration(booking.service.duration_min)}`}
        />
        {booking.address && <Row title="Место" subtitle={booking.address} />}
      </Section>
      {error && <ErrorText>{error}</ErrorText>}
      {pending && (
        <Section>
          <Row
            title={busy === 'decline' ? 'Отклоняем…' : 'Отклонить'}
            tone="destructive"
            onClick={busy ? undefined : () => void act('decline')}
          />
        </Section>
      )}
      {!pending && booking.can_cancel && (
        <Section>
          <Row
            title={busy === 'cancel' ? 'Отменяем…' : 'Отменить запись'}
            tone="destructive"
            onClick={busy ? undefined : () => void act('cancel')}
          />
        </Section>
      )}
      <MainButton
        text="Подтвердить запись"
        onClick={() => void act('confirm')}
        visible={pending}
        disabled={busy !== null && busy !== 'confirm'}
        loading={busy === 'confirm'}
      />
    </Screen>
  )
}
