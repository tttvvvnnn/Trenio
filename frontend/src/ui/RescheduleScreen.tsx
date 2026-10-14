import { useState } from 'react'

import { type Booking, type Slot } from '../api'
import { dateTime, localDate } from '../format'
import { haptic } from '../telegram'
import CommentField from './CommentField'
import { ErrorText } from './kit'
import { MainButton } from './native'
import Screen from './Screen'
import SlotPicker from './SlotPicker'

type Props = {
  booking: Booking
  // Окошки той же услуги, где время самой записи считается свободным
  loadSlots: (from: string, count: number) => Promise<Slot[]>
  // Тренер переносит на любое время, клиент — только в окошко
  allowCustom: boolean
  // Подсказка под выбором: кто что увидит
  footer: string
  onBack: () => void
  onSubmit: (startsAt: string, comment: string) => Promise<Booking>
  onDone: (booking: Booking) => void
}

/** Перенос записи на другое время. Это та же запись: блок и история сохраняются. */
export default function RescheduleScreen({
  booking,
  loadSlots,
  allowCustom,
  footer,
  onBack,
  onSubmit,
  onDone,
}: Props) {
  const timezone = booking.trainer.timezone
  const [startsAt, setStartsAt] = useState<string | null>(null)
  const [comment, setComment] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reloads, setReloads] = useState(0)

  async function submit() {
    if (startsAt === null || saving) return
    setSaving(true)
    setError(null)
    try {
      const updated = await onSubmit(startsAt, comment.trim())
      haptic.success()
      onDone(updated)
    } catch (err) {
      haptic.error()
      setError(err instanceof Error ? err.message : String(err))
      // Окошко могли занять, пока выбирали: показываем свежие
      setStartsAt(null)
      setReloads((count) => count + 1)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Screen
      title="Перенести запись"
      subtitle={`${booking.service.name} · сейчас ${dateTime(booking.starts_at, timezone)}`}
      onBack={onBack}
    >
      <SlotPicker
        timezone={timezone}
        capacity={booking.service.capacity}
        load={async (from, count) =>
          // Нынешнее время записи свободно для неё самой, но переносить на него незачем
          (await loadSlots(from, count)).filter((slot) => slot.starts_at !== booking.starts_at)
        }
        reloadKey={String(reloads)}
        value={startsAt}
        onChange={setStartsAt}
        allowCustom={allowCustom}
        initialDay={localDate(booking.starts_at, timezone)}
      />
      <CommentField
        value={comment}
        onChange={setComment}
        placeholder="Например: задерживаюсь на работе"
        footer={footer}
      />
      {error && <ErrorText>{error}</ErrorText>}
      <MainButton
        text={startsAt ? `Перенести на ${dateTime(startsAt, timezone)}` : 'Перенести'}
        onClick={() => void submit()}
        visible={startsAt !== null}
        loading={saving}
      />
    </Screen>
  )
}
