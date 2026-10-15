import { useState } from 'react'

import { errorText, updateTrainer, type Trainer } from '../api'
import { deviceTimezone, timezoneOptions } from '../format'
import { haptic } from '../telegram'
import { ErrorText, InlineField, PageHeader, Section, TextField } from '../ui/kit'
import MyPhoto from '../ui/MyPhoto'
import { MainButton } from '../ui/native'

type Props = {
  trainer: Trainer
  // Онбординг: короткая форма и подсказки для первого входа
  onboarding?: boolean
  onSaved: (trainer: Trainer) => void
}

/** Как тренера видят клиенты: фото, имя, адрес зала и часовой пояс. */
export default function ProfileForm({ trainer, onboarding = false, onSaved }: Props) {
  const [displayName, setDisplayName] = useState(trainer.display_name)
  // При первом входе подставляем часовой пояс телефона, если он из списка
  const [timezone, setTimezone] = useState(() => {
    if (!onboarding) return trainer.timezone
    const device = deviceTimezone()
    return timezoneOptions(trainer.timezone).some(([value]) => value === device)
      ? device
      : trainer.timezone
  })
  const [address, setAddress] = useState(trainer.address ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const dirty =
    displayName.trim() !== trainer.display_name ||
    timezone !== trainer.timezone ||
    address.trim() !== (trainer.address ?? '')
  const valid = displayName.trim() !== ''

  async function submit() {
    if (!valid || saving) return
    setSaving(true)
    setError(null)
    try {
      const updated = await updateTrainer({
        display_name: displayName.trim(),
        timezone,
        address: address.trim(),
      })
      haptic.success()
      onSaved(updated)
    } catch (err) {
      haptic.error()
      setError(errorText(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        void submit()
      }}
    >
      {onboarding ? (
        <PageHeader
          title="Добро пожаловать в Trenio!"
          subtitle="Пара вопросов, чтобы настроить профиль. Всё можно поменять позже в «Профиле»."
        />
      ) : (
        <MyPhoto
          variant="hero"
          name={displayName.trim() || trainer.display_name}
          seed={trainer.id}
          caption="Так вас видят клиенты"
        />
      )}
      <TextField
        label="Имя, которое увидят клиенты"
        value={displayName}
        onChange={setDisplayName}
        maxLength={128}
        required
      />
      <TextField
        label="Адрес зала"
        value={address}
        onChange={setAddress}
        placeholder="ул. Ленина, 1, фитнес-клуб «Сила»"
        maxLength={256}
        footer="Клиенты увидят его в записи. У отдельной услуги можно указать другое место."
      />
      <Section footer="Время в окошках и напоминаниях считается по этому поясу.">
        <InlineField label="Часовой пояс" icon={{ name: 'globe', color: 'var(--c-violet)' }}>
          {(id) => (
            <select
              id={id}
              className="row-input"
              value={timezone}
              onChange={(event) => setTimezone(event.target.value)}
            >
              {timezoneOptions(trainer.timezone).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          )}
        </InlineField>
      </Section>
      {error && <ErrorText>{error}</ErrorText>}
      <MainButton
        text={onboarding ? 'Продолжить' : 'Сохранить'}
        onClick={() => void submit()}
        visible={onboarding || dirty}
        disabled={!valid}
        loading={saving}
      />
    </form>
  )
}
