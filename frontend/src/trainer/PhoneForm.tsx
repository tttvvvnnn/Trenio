import { useState } from 'react'

import { errorText, saveClientPhone } from '../api'
import { haptic } from '../telegram'
import { ErrorText, Row, Section, SwitchRow, TextField } from '../ui/kit'
import { MainButton } from '../ui/native'
import Screen from '../ui/Screen'
import { withUndo } from '../undo'

type Props = {
  clientId: number
  clientName: string
  phone: string | null
  onBack: () => void
  onSaved: (phone: string | null) => void
}

/** Телефон клиента: видит только тренер, хранится только с согласия клиента. */
export default function PhoneForm({ clientId, clientName, phone, onBack, onSaved }: Props) {
  const [value, setValue] = useState(phone ?? '')
  // Согласие уже давали, если телефон сохранён
  const [consent, setConsent] = useState(phone !== null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const valid = value.trim() !== '' && consent

  async function save(next: string | null) {
    if (saving) return
    setSaving(true)
    setError(null)
    try {
      const saved = await saveClientPhone(clientId, next, consent)
      haptic.success()
      onSaved(saved.phone)
    } catch (err) {
      haptic.error()
      setError(errorText(err))
      setSaving(false)
    }
  }

  function remove() {
    haptic.success()
    onSaved(null)
    withUndo({
      text: 'Телефон удалён',
      commit: () => saveClientPhone(clientId, null, consent),
      undo: () => onSaved(phone),
    })
  }

  return (
    <Screen title="Телефон" subtitle={clientName} onBack={onBack}>
      <TextField
        label="Номер"
        value={value}
        onChange={setValue}
        placeholder="+7 900 000-00-00"
        type="tel"
        inputMode="tel"
        autoComplete="tel"
        maxLength={32}
        footer="Видите только вы. Клиент видит свой номер в Профиле и может его удалить."
      />
      <Section footer="По закону о персональных данных телефон можно хранить, только если клиент не против.">
        <SwitchRow
          label="Клиент согласен"
          subtitle="Он разрешил хранить свой телефон в Trenio"
          icon={{ name: 'shield', color: 'var(--c-success)' }}
          checked={consent}
          onChange={setConsent}
        />
      </Section>
      {phone !== null && (
        <Section>
          <Row title="Удалить телефон" tone="destructive" onClick={saving ? undefined : remove} />
        </Section>
      )}
      {error && <ErrorText>{error}</ErrorText>}
      <MainButton
        text="Сохранить"
        onClick={() => void save(value.trim())}
        disabled={!valid}
        loading={saving}
      />
    </Screen>
  )
}
