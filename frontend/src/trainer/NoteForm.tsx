import { useId, useState } from 'react'

import { saveBookingNote, type Booking } from '../api'
import { dateTime } from '../format'
import { confirmAction, haptic } from '../telegram'
import { ErrorText, Row, Section, SwitchRow } from '../ui/kit'
import { MainButton } from '../ui/native'
import Screen from '../ui/Screen'

type Props = {
  booking: Booking
  onBack: () => void
  onSaved: (booking: Booking) => void
}

// Как на сервере
const MAX_NOTE = 2000

/** Заметка к занятию: что делали. Клиент её видит, если не отметить «только для меня». */
export default function NoteForm({ booking, onBack, onSaved }: Props) {
  const id = useId()
  const [note, setNote] = useState(booking.note ?? '')
  const [isPrivate, setPrivate] = useState(booking.note_private)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function save(text: string | null) {
    if (saving) return
    setSaving(true)
    setError(null)
    try {
      const updated = await saveBookingNote(booking.id, text, isPrivate)
      haptic.success()
      onSaved(updated)
    } catch (err) {
      haptic.error()
      setError(err instanceof Error ? err.message : String(err))
      setSaving(false)
    }
  }

  async function remove() {
    if (await confirmAction('Удалить заметку к занятию?', 'Удалить')) void save(null)
  }

  return (
    <Screen
      title="Заметка к занятию"
      subtitle={dateTime(booking.starts_at, booking.trainer.timezone)}
      onBack={onBack}
    >
      <section className="section">
        <label className="section-title" htmlFor={id}>
          Что делали
        </label>
        <div className="group">
          <textarea
            id={id}
            className="field-input"
            placeholder="Упражнения, веса, самочувствие, домашнее задание"
            maxLength={MAX_NOTE}
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />
        </div>
      </section>
      <Section
        footer={
          isPrivate
            ? 'Заметку видите только вы.'
            : 'Клиент увидит заметку в своих записях. Уведомление ему не придёт.'
        }
      >
        <SwitchRow
          label="Только для меня"
          icon={{ name: 'shield', color: 'var(--c-violet)' }}
          checked={isPrivate}
          onChange={setPrivate}
        />
      </Section>
      {booking.note !== null && (
        <Section>
          <Row
            title="Удалить заметку"
            tone="destructive"
            onClick={saving ? undefined : () => void remove()}
          />
        </Section>
      )}
      {error && <ErrorText>{error}</ErrorText>}
      <MainButton
        text="Сохранить"
        onClick={() => void save(note.trim() || null)}
        disabled={note.trim() === '' && booking.note === null}
        loading={saving}
      />
    </Screen>
  )
}
