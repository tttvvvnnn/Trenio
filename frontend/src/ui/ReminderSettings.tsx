import { useEffect, useState } from 'react'

import {
  errorText,
  fetchReminders,
  saveReminders,
  type ReminderPrefs,
  type ReminderRole,
} from '../api'
import { REMINDER_OFFSETS } from '../settings'
import { haptic } from '../telegram'
import { ErrorText, MultiChips, Section, SkeletonList, SwitchRow } from './kit'

// Столько напоминаний об одном занятии принимает сервер
const MAX_OFFSETS = 4

const FOOTER: Record<ReminderRole, string> = {
  client: 'Бот напомнит о тренировке. О подтверждении и отмене записи он пишет всегда.',
  trainer:
    'О новых записях и отменах бот пишет всегда. Напоминания — о занятиях, которые вы проводите.',
}

type Props = {
  role: ReminderRole
}

// Настройки сохраняются сразу при каждом изменении
export default function ReminderSettings({ role }: Props) {
  const [prefs, setPrefs] = useState<ReminderPrefs | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchReminders()
      .then((all) => setPrefs(role === 'trainer' ? all.trainer : all.client))
      .catch((err: unknown) => setError(errorText(err)))
  }, [role])

  async function update(next: ReminderPrefs) {
    if (prefs === null) return
    const previous = prefs
    setPrefs(next)
    setError(null)
    try {
      setPrefs(await saveReminders(role, next))
    } catch (err) {
      haptic.error()
      setPrefs(previous)
      setError(errorText(err))
    }
  }

  function toggleOffset(offset: number) {
    if (prefs === null) return
    const has = prefs.offsets.includes(offset)
    if (!has && prefs.offsets.length >= MAX_OFFSETS) {
      haptic.error()
      return
    }
    const offsets = has
      ? prefs.offsets.filter((value) => value !== offset)
      : [...prefs.offsets, offset]
    void update({ ...prefs, offsets: offsets.sort((a, b) => b - a) })
  }

  const selected = prefs?.offsets ?? []
  return (
    <>
      <Section title="Уведомления" footer={FOOTER[role]}>
        {prefs === null && !error && <SkeletonList rows={1} />}
        {prefs !== null && (
          <>
            <SwitchRow
              label="Напоминать о занятиях"
              subtitle={prefs.enabled && selected.length === 0 ? 'Выберите, когда' : undefined}
              icon={{ name: 'bell', color: 'var(--c-warning)' }}
              checked={prefs.enabled}
              onChange={(enabled) => void update({ ...prefs, enabled })}
            />
            {prefs.enabled && (
              <MultiChips
                label="Когда напомнить"
                values={selected}
                options={REMINDER_OFFSETS}
                onToggle={toggleOffset}
              />
            )}
            {role === 'trainer' && (
              <SwitchRow
                label="Просить отметить занятие"
                subtitle="После занятия бот спросит: прошла или пропуск"
                icon={{ name: 'check', color: 'var(--c-success)' }}
                checked={prefs.attendance_prompt}
                onChange={(attendance_prompt) => void update({ ...prefs, attendance_prompt })}
              />
            )}
          </>
        )}
      </Section>
      {error && <ErrorText>{error}</ErrorText>}
    </>
  )
}
