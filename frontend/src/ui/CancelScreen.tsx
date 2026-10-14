import { useState } from 'react'

import type { Booking } from '../api'
import { dateTime } from '../format'
import { haptic } from '../telegram'
import CommentField from './CommentField'
import { ErrorText } from './kit'
import { MainButton } from './native'
import Screen from './Screen'

type Props = {
  booking: Booking
  // Отмена или отклонение неподтверждённой записи
  action: 'cancel' | 'decline'
  // Кому уйдёт комментарий
  recipient: string
  onBack: () => void
  onSubmit: (comment: string) => Promise<Booking>
  onDone: (booking: Booking) => void
}

/** Отмена записи с необязательным комментарием для второй стороны. */
export default function CancelScreen({
  booking,
  action,
  recipient,
  onBack,
  onSubmit,
  onDone,
}: Props) {
  const [comment, setComment] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit() {
    if (saving) return
    setSaving(true)
    setError(null)
    try {
      const updated = await onSubmit(comment.trim())
      haptic.success()
      onDone(updated)
    } catch (err) {
      haptic.error()
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  const title = action === 'cancel' ? 'Отменить запись' : 'Отклонить запись'
  return (
    <Screen
      title={title}
      subtitle={`${booking.service.name} · ${dateTime(booking.starts_at, booking.trainer.timezone)}`}
      onBack={onBack}
    >
      <CommentField
        value={comment}
        onChange={setComment}
        placeholder="Например: заболел, давайте перенесём на четверг"
        footer={`Необязательно. ${recipient} увидит комментарий в приложении и в уведомлении. Время освободится для других.`}
      />
      {error && <ErrorText>{error}</ErrorText>}
      <MainButton text={title} onClick={() => void submit()} loading={saving} />
    </Screen>
  )
}
