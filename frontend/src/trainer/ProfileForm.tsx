import { useState, type FormEvent } from 'react'

import { updateTrainer, type Trainer } from '../api'
import { deviceTimezone, timezoneOptions } from '../format'

type Props = {
  trainer: Trainer
  // Онбординг: короткая форма и подсказки для первого входа
  onboarding?: boolean
  onSaved: (trainer: Trainer) => void
}

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
  const [autoConfirm, setAutoConfirm] = useState(trainer.auto_confirm)
  const [cancelHours, setCancelHours] = useState(String(trainer.cancel_hours))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      const updated = await updateTrainer({
        display_name: displayName.trim(),
        timezone,
        address: address.trim(),
        auto_confirm: autoConfirm,
        cancel_hours: Number(cancelHours),
      })
      setSaved(true)
      onSaved(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="form" onSubmit={submit}>
      <label>
        Имя, которое увидят клиенты
        <input
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
          maxLength={128}
          required
        />
      </label>
      <label>
        Часовой пояс
        <select value={timezone} onChange={(event) => setTimezone(event.target.value)}>
          {timezoneOptions(trainer.timezone).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Адрес зала
        <input
          value={address}
          onChange={(event) => setAddress(event.target.value)}
          placeholder="Например, ул. Ленина, 1, фитнес-клуб «Сила»"
          maxLength={256}
        />
      </label>
      {!onboarding && (
        <>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={autoConfirm}
              onChange={(event) => setAutoConfirm(event.target.checked)}
            />
            Подтверждать записи автоматически
          </label>
          <label>
            Клиент может отменить запись не позже чем за, часов
            <input
              type="number"
              min={0}
              max={168}
              value={cancelHours}
              onChange={(event) => setCancelHours(event.target.value)}
              required
            />
          </label>
        </>
      )}
      {error && <p className="error">{error}</p>}
      {saved && !onboarding && <p className="hint">Сохранено</p>}
      <button type="submit" disabled={saving}>
        {onboarding ? 'Продолжить' : 'Сохранить'}
      </button>
    </form>
  )
}
