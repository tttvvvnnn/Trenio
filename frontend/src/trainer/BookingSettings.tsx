import { useState } from 'react'

import { errorText, updateTrainer, type OneOffMode, type Trainer } from '../api'
import { SLOT_STEPS } from '../settings'
import { haptic } from '../telegram'
import { ErrorText, InlineField, Row, Section, Stepper, SwitchRow } from '../ui/kit'
import { MainButton } from '../ui/native'
import Screen from '../ui/Screen'

// За сколько часов до начала клиент ещё может отменить запись
const CANCEL_HOURS = [0, 1, 2, 3, 4, 6, 8, 12, 24, 36, 48, 72, 168]

// Запись клиента без блока
const ONE_OFF_MODES: [OneOffMode, string][] = [
  ['allow', 'разрешать'],
  ['confirm', 'с моим подтверждением'],
  ['forbid', 'только по блоку'],
]

const ONE_OFF_FOOTER: Record<OneOffMode, string> = {
  allow: 'Клиент может записаться, даже если блока нет или он закончился.',
  confirm: 'Если блока на занятие не хватает, запись ждёт вашего подтверждения.',
  forbid: 'Без свободного занятия в блоке клиент записаться не сможет. Вы записываете кого угодно.',
}

// 795 -> "13:15"
function clock(minutes: number): string {
  return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}`
}

type Props = {
  trainer: Trainer
  onBack: () => void
  onSaved: (trainer: Trainer) => void
}

/** Как клиенты записываются: подтверждение, срок отмены, шаг времени и запись без блока. */
export default function BookingSettings({ trainer, onBack, onSaved }: Props) {
  const [autoConfirm, setAutoConfirm] = useState(trainer.auto_confirm)
  const [cancelHours, setCancelHours] = useState(trainer.cancel_hours)
  const [slotStep, setSlotStep] = useState(trainer.slot_step_min)
  const [oneOffMode, setOneOffMode] = useState(trainer.one_off_mode)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const dirty =
    autoConfirm !== trainer.auto_confirm ||
    cancelHours !== trainer.cancel_hours ||
    slotStep !== trainer.slot_step_min ||
    oneOffMode !== trainer.one_off_mode

  async function submit() {
    if (saving) return
    setSaving(true)
    setError(null)
    try {
      const updated = await updateTrainer({
        auto_confirm: autoConfirm,
        cancel_hours: cancelHours,
        slot_step_min: slotStep,
        one_off_mode: oneOffMode,
      })
      haptic.success()
      onSaved(updated)
    } catch (err) {
      haptic.error()
      setError(errorText(err))
      setSaving(false)
    }
  }

  return (
    <Screen title="Как клиенты записываются" onBack={onBack}>
      <Section
        footer={
          cancelHours === 0
            ? 'Клиент может отменить запись в любой момент до начала.'
            : `Позже чем за ${cancelHours} ч до начала клиент отменить запись не сможет, только написать вам.`
        }
      >
        <SwitchRow
          label="Подтверждать сразу"
          subtitle={
            autoConfirm ? 'Запись подтверждается без вас' : 'Каждую запись подтверждаете вы'
          }
          icon={{ name: 'check', color: 'var(--c-success)' }}
          checked={autoConfirm}
          onChange={setAutoConfirm}
        />
        <Row
          title="Срок отмены"
          icon={{ name: 'clock', color: 'var(--c-destructive)' }}
          after={
            <Stepper
              label="Отмена клиентом, часов до начала"
              value={cancelHours}
              options={CANCEL_HOURS}
              onChange={setCancelHours}
              format={(value) => `${value} ч`}
            />
          }
        />
      </Section>
      <Section
        footer={
          slotStep === 0
            ? 'Начала идут подряд: часовая услуга в 10:00, 11:00, 12:00.'
            : `Клиент выбирает начало с шагом ${slotStep} мин, например 13:00 или ${clock(13 * 60 + slotStep)}. Занятие целиком помещается в рабочее время.`
        }
      >
        <InlineField label="Время начала" icon={{ name: 'calendar', color: 'var(--c-accent)' }}>
          {(id) => (
            <select
              id={id}
              className="row-input"
              value={slotStep}
              onChange={(event) => setSlotStep(Number(event.target.value))}
            >
              {SLOT_STEPS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          )}
        </InlineField>
      </Section>
      <Section footer={ONE_OFF_FOOTER[oneOffMode]}>
        <InlineField label="Без блока" icon={{ name: 'ticket', color: 'var(--c-warning)' }}>
          {(id) => (
            <select
              id={id}
              className="row-input"
              value={oneOffMode}
              onChange={(event) => setOneOffMode(event.target.value as OneOffMode)}
            >
              {ONE_OFF_MODES.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          )}
        </InlineField>
      </Section>
      {error && <ErrorText>{error}</ErrorText>}
      <MainButton text="Сохранить" onClick={() => void submit()} visible={dirty} loading={saving} />
    </Screen>
  )
}
