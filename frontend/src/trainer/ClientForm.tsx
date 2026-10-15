import { useState } from 'react'

import { createClient, renameClient, type Client } from '../api'
import { haptic } from '../telegram'
import { ErrorText, TextField } from '../ui/kit'
import { MainButton } from '../ui/native'
import Screen from '../ui/Screen'

type Props = {
  // Есть — правим имя этого клиента, нет — заводим нового
  client?: Client
  onBack: () => void
  onSaved: (client: Client) => void
}

/** Клиент без Telegram: тренер заводит его сам или правит имя. */
export default function ClientForm({ client, onBack, onSaved }: Props) {
  const [firstName, setFirstName] = useState(client?.first_name ?? '')
  const [lastName, setLastName] = useState(client?.last_name ?? '')
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const valid = firstName.trim() !== ''

  async function submit() {
    if (!valid || saving) return
    setSaving(true)
    setError(null)
    const name = { first_name: firstName.trim(), last_name: lastName.trim() || null }
    try {
      const saved = client
        ? await renameClient(client.id, name)
        : await createClient({ ...name, notes: notes.trim() || null })
      haptic.success()
      onSaved(saved)
    } catch (err) {
      haptic.error()
      setError(err instanceof Error ? err.message : String(err))
      setSaving(false)
    }
  }

  return (
    <Screen title={client ? 'Имя клиента' : 'Новый клиент'} onBack={onBack}>
      <TextField
        label="Имя"
        value={firstName}
        onChange={setFirstName}
        placeholder="Мария"
        maxLength={128}
        required
      />
      <TextField
        label="Фамилия"
        value={lastName}
        onChange={setLastName}
        placeholder="Необязательно"
        maxLength={128}
      />
      {!client && (
        <section className="section">
          <label className="section-title" htmlFor="new-client-notes">
            Заметка
          </label>
          <div className="group">
            <textarea
              id="new-client-notes"
              className="field-input"
              placeholder="Цели, ограничения. Клиент заметки не видит."
              maxLength={4000}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
            />
          </div>
          <p className="section-footer">
            Клиенту не нужен Telegram: вы записываете его на занятия и ведёте блоки сами.
            Напоминания ему не приходят. Если он потом подключится, отправьте ему личную ссылку из
            карточки, и вся история перейдёт к нему.
          </p>
        </section>
      )}
      {error && <ErrorText>{error}</ErrorText>}
      <MainButton
        text={client ? 'Сохранить' : 'Добавить клиента'}
        onClick={() => void submit()}
        disabled={!valid}
        loading={saving}
      />
    </Screen>
  )
}
