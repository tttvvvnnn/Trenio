import { useState } from 'react'

import { errorText, acceptTrainerRules, type ClientTrainer } from '../api'
import { haptic } from '../telegram'
import { ErrorText, PageHeader, Section } from './kit'
import { MainButton } from './native'
import Screen from './Screen'

/** Текст правил тренера как есть, с его переносами строк. */
export function RulesText({ text }: { text: string }) {
  return (
    <Section>
      <p className="rules-text">{text}</p>
    </Section>
  )
}

/** Правила тренера для клиента: открываются из «Записи» в любой момент. */
export function RulesScreen({ trainer, onBack }: { trainer: ClientTrainer; onBack: () => void }) {
  return (
    <Screen title="Правила занятий" subtitle={trainer.display_name} onBack={onBack}>
      <RulesText text={trainer.rules ?? ''} />
    </Screen>
  )
}

type GateProps = {
  trainer: ClientTrainer
  onAccepted: (trainer: ClientTrainer) => void
}

/** Новые или изменённые правила: без согласия клиент к тренеру не записывается. */
export function RulesGate({ trainer, onAccepted }: GateProps) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function accept() {
    if (saving) return
    setSaving(true)
    setError(null)
    try {
      const updated = await acceptTrainerRules(trainer.id)
      haptic.success()
      onAccepted(updated)
    } catch (err) {
      haptic.error()
      setError(errorText(err))
      setSaving(false)
    }
  }

  return (
    <>
      <PageHeader
        title="Правила занятий"
        subtitle={`${trainer.display_name} просит прочитать их перед записью.`}
      />
      <RulesText text={trainer.rules ?? ''} />
      {error && <ErrorText>{error}</ErrorText>}
      <MainButton text="Прочитал и согласен" onClick={() => void accept()} loading={saving} />
    </>
  )
}
