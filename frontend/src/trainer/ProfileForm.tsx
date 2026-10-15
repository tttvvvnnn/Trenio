import { useState } from 'react'

import { updateTrainer, type Trainer } from '../api'
import { deviceTimezone, timezoneOptions } from '../format'
import { haptic } from '../telegram'
import {
  ErrorText,
  InlineField,
  PageHeader,
  Row,
  Section,
  Stepper,
  SwitchRow,
  TextField,
} from '../ui/kit'
import MyPhoto from '../ui/MyPhoto'
import { MainButton } from '../ui/native'
import ReminderSettings from '../ui/ReminderSettings'
import { TourRow } from '../ui/Tour'
import RulesEditor from './RulesEditor'

// За сколько часов до начала клиент ещё может отменить запись
const CANCEL_HOURS = [0, 1, 2, 3, 4, 6, 8, 12, 24, 36, 48, 72, 168]

// С каким шагом клиенту предлагается время начала; 0 — по длительности услуги
const SLOT_STEPS: [number, string][] = [
  [5, 'каждые 5 мин'],
  [10, 'каждые 10 мин'],
  [15, 'каждые 15 мин'],
  [20, 'каждые 20 мин'],
  [30, 'каждые 30 мин'],
  [60, 'каждый час'],
  [0, 'по длительности услуги'],
]

type Props = {
  trainer: Trainer
  // Онбординг: короткая форма и подсказки для первого входа
  onboarding?: boolean
  onSaved: (trainer: Trainer) => void
  // Услуги и шаблоны блоков: отдельный экран
  onOpenServices?: () => void
  // Есть только у админа
  onOpenAdmin?: () => void
  // Есть, когда тренер сам записан к другому тренеру
  onSwitchToClient?: () => void
  // Запустить вводный тур заново
  onStartTour?: () => void
}

// 795 -> "13:15"
function clock(minutes: number): string {
  return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}`
}

export default function ProfileForm({
  trainer,
  onboarding = false,
  onSaved,
  onOpenServices,
  onOpenAdmin,
  onSwitchToClient,
  onStartTour,
}: Props) {
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
  const [cancelHours, setCancelHours] = useState(trainer.cancel_hours)
  const [slotStep, setSlotStep] = useState(trainer.slot_step_min)
  const [rulesOpen, setRulesOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const dirty =
    displayName.trim() !== trainer.display_name ||
    timezone !== trainer.timezone ||
    address.trim() !== (trainer.address ?? '') ||
    autoConfirm !== trainer.auto_confirm ||
    cancelHours !== trainer.cancel_hours ||
    slotStep !== trainer.slot_step_min
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
        auto_confirm: autoConfirm,
        cancel_hours: cancelHours,
        slot_step_min: slotStep,
      })
      haptic.success()
      onSaved(updated)
    } catch (err) {
      haptic.error()
      setError(err instanceof Error ? err.message : String(err))
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
      {!onboarding && (
        <Section
          title="Записи"
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
      )}
      {!onboarding && (
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
      )}
      {!onboarding && onOpenAdmin && (
        <Section footer="Видите только вы: тренеры, клиенты и общие цифры платформы.">
          <Row
            title="Админ-панель"
            icon={{ name: 'users', color: 'var(--c-planned)' }}
            chevron
            onClick={onOpenAdmin}
          />
        </Section>
      )}
      {!onboarding && onOpenServices && (
        <Section footer="На услуги клиенты записываются, шаблоны блоков помогают их продавать.">
          <Row
            title="Услуги и блоки"
            tourId="services"
            icon={{ name: 'ticket', color: 'var(--c-violet)' }}
            chevron
            onClick={onOpenServices}
          />
        </Section>
      )}
      {!onboarding && (
        <Section footer="Клиент читает их и соглашается перед первой записью.">
          <Row
            title="Правила занятий"
            subtitle={trainer.rules ? undefined : 'Не заполнены'}
            icon={{ name: 'list', color: 'var(--c-warning)' }}
            chevron
            onClick={() => setRulesOpen(true)}
          />
        </Section>
      )}
      {!onboarding && <ReminderSettings role="trainer" />}
      {!onboarding && onStartTour && <TourRow onClick={onStartTour} />}
      {onSwitchToClient && !onboarding && (
        <Section footer="Ваши записи к другим тренерам.">
          <Row
            title="Профиль клиента"
            icon={{ name: 'calendar', color: 'var(--c-accent)' }}
            chevron
            onClick={onSwitchToClient}
          />
        </Section>
      )}
      {error && <ErrorText>{error}</ErrorText>}
      {rulesOpen && (
        <RulesEditor trainer={trainer} onSaved={onSaved} onBack={() => setRulesOpen(false)} />
      )}
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
