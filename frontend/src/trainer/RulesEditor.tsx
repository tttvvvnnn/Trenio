import { useState } from 'react'

import { updateTrainer, type Trainer } from '../api'
import { haptic } from '../telegram'
import { ErrorText } from '../ui/kit'
import { MainButton } from '../ui/native'
import Screen from '../ui/Screen'

type Props = {
  trainer: Trainer
  onSaved: (trainer: Trainer) => void
  onBack: () => void
}

/** Правила занятий тренера: клиенты подтверждают их перед первой записью. */
export default function RulesEditor({ trainer, onSaved, onBack }: Props) {
  const [rules, setRules] = useState(trainer.rules ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const dirty = rules.trim() !== (trainer.rules ?? '')

  async function save() {
    if (!dirty || saving) return
    setSaving(true)
    setError(null)
    try {
      const updated = await updateTrainer({ rules: rules.trim() })
      haptic.success()
      onSaved(updated)
      onBack()
    } catch (err) {
      haptic.error()
      setError(err instanceof Error ? err.message : String(err))
      setSaving(false)
    }
  }

  return (
    <Screen title="Правила занятий" onBack={onBack}>
      <section className="section">
        <div className="group">
          <textarea
            className="field-input rules-input"
            aria-label="Правила занятий"
            placeholder={
              'Например:\n— отмена не позже чем за 12 часов, иначе занятие списывается\n— опоздание сокращает занятие\n— блок действует 2 месяца'
            }
            maxLength={4000}
            value={rules}
            onChange={(event) => setRules(event.target.value)}
          />
        </div>
        <p className="section-footer">
          Каждый клиент прочитает правила и нажмёт «Прочитал и согласен» перед записью. После
          изменения клиенты подтвердят их снова. Пустое поле — правил нет.
        </p>
      </section>
      {error && <ErrorText>{error}</ErrorText>}
      <MainButton text="Сохранить" onClick={() => void save()} visible={dirty} loading={saving} />
    </Screen>
  )
}
