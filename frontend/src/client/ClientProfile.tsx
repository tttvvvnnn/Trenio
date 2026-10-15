import { useEffect, useState } from 'react'

import {
  errorText,
  fetchMe,
  removeMyPhone,
  resetMyName,
  saveMyName,
  type ClientTrainer,
  type Me,
  type MyName,
} from '../api'
import { fullName } from '../format'
import { confirmAction, haptic } from '../telegram'
import { TrainerAvatar } from '../ui/Avatar'
import { ErrorText, InlineField, Row, Section, SkeletonList } from '../ui/kit'
import MyPhoto from '../ui/MyPhoto'
import { PrivacySection } from '../ui/Privacy'
import ReminderSettings from '../ui/ReminderSettings'
import { RulesScreen } from '../ui/Rules'
import { TourRow } from '../ui/Tour'

type Props = {
  trainers: ClientTrainer[] | null
  // Есть, когда человек ещё и тренер
  onSwitchToTrainer?: () => void
  // Запустить вводный тур заново
  onStartTour?: () => void
}

/** Профиль клиента: фото и имя, которые видит тренер, тренеры с правилами, напоминания. */
export default function ClientProfile({ trainers, onSwitchToTrainer, onStartTour }: Props) {
  const [me, setMe] = useState<Me | null>(null)
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [saving, setSaving] = useState(false)
  const [rulesOf, setRulesOf] = useState<ClientTrainer | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Тренеры, у которых клиент только что удалил свой телефон
  const [phonesRemoved, setPhonesRemoved] = useState<number[]>([])

  useEffect(() => {
    fetchMe()
      .then((loaded) => {
        setMe(loaded)
        setFirstName(loaded.first_name)
        setLastName(loaded.last_name ?? '')
      })
      .catch((err: unknown) => setError(errorText(err)))
  }, [])

  async function save(action: () => Promise<MyName>) {
    if (me === null) return
    setSaving(true)
    setError(null)
    try {
      const name = await action()
      setMe({ ...me, ...name })
      setFirstName(name.first_name)
      setLastName(name.last_name ?? '')
      haptic.success()
    } catch (err) {
      haptic.error()
      setError(errorText(err))
    } finally {
      setSaving(false)
    }
  }

  // Сохраняем, когда поле теряет фокус и имя правда поменялось
  function saveIfChanged() {
    if (me === null) return
    const first = firstName.trim()
    const last = lastName.trim() || null
    if (!first) {
      setFirstName(me.first_name)
      return
    }
    if (first === me.first_name && last === me.last_name) return
    void save(() => saveMyName(first, last))
  }

  async function removePhone(trainer: ClientTrainer) {
    const sure = await confirmAction(
      `Удалить ваш телефон у тренера ${trainer.display_name}?`,
      'Удалить',
    )
    if (!sure) return
    setError(null)
    try {
      await removeMyPhone(trainer.id)
      haptic.success()
      setPhonesRemoved((ids) => [...ids, trainer.id])
    } catch (err) {
      haptic.error()
      setError(errorText(err))
    }
  }

  if (me === null) {
    return error ? <ErrorText>{error}</ErrorText> : <SkeletonList rows={3} />
  }

  const withRules = trainers?.filter((trainer) => trainer.rules) ?? []
  const withPhone =
    trainers?.filter((trainer) => trainer.my_phone && !phonesRemoved.includes(trainer.id)) ?? []
  const shownName = fullName({ first_name: firstName.trim() || me.first_name, last_name: lastName })

  return (
    <>
      <MyPhoto variant="hero" name={shownName} seed={me.id} caption="Так вас видит тренер" />
      <Section
        title="Имя для тренера"
        footer={
          me.name_custom
            ? 'Своё имя: Telegram его больше не поменяет.'
            : 'Сейчас имя из Telegram. Поменяйте, если тренер знает вас по-другому.'
        }
      >
        <InlineField label="Имя">
          {(id) => (
            <input
              id={id}
              className="row-input"
              value={firstName}
              maxLength={128}
              autoComplete="given-name"
              disabled={saving}
              onChange={(event) => setFirstName(event.target.value)}
              onBlur={saveIfChanged}
            />
          )}
        </InlineField>
        <InlineField label="Фамилия">
          {(id) => (
            <input
              id={id}
              className="row-input"
              value={lastName}
              placeholder="Необязательно"
              maxLength={128}
              autoComplete="family-name"
              disabled={saving}
              onChange={(event) => setLastName(event.target.value)}
              onBlur={saveIfChanged}
            />
          )}
        </InlineField>
        {me.name_custom && (
          <Row
            title="Вернуть имя из Telegram"
            tone="accent"
            onClick={saving ? undefined : () => void save(resetMyName)}
          />
        )}
      </Section>
      {error && <ErrorText>{error}</ErrorText>}
      {trainers !== null && trainers.length > 0 && (
        <Section title={trainers.length > 1 ? 'Мои тренеры' : 'Мой тренер'}>
          {trainers.map((trainer) => (
            <Row
              key={trainer.id}
              leading={<TrainerAvatar trainer={trainer} />}
              title={trainer.display_name}
              subtitle={trainer.address ?? undefined}
            />
          ))}
          {withRules.map((trainer) => (
            <Row
              key={`rules-${trainer.id}`}
              title="Правила занятий"
              subtitle={trainers.length > 1 ? trainer.display_name : undefined}
              icon={{ name: 'list', color: 'var(--c-warning)' }}
              chevron
              onClick={() => setRulesOf(trainer)}
            />
          ))}
          {withPhone.map((trainer) => (
            <Row
              key={`phone-${trainer.id}`}
              title={trainer.my_phone ?? ''}
              subtitle={
                trainers.length > 1
                  ? `Ваш телефон у тренера ${trainer.display_name}`
                  : 'Ваш телефон у тренера'
              }
              icon={{ name: 'phone', color: 'var(--c-success)' }}
              after={
                <button
                  type="button"
                  className="row-action destructive"
                  onClick={() => void removePhone(trainer)}
                >
                  Удалить
                </button>
              }
            />
          ))}
        </Section>
      )}
      <ReminderSettings role="client" />
      {onStartTour && <TourRow onClick={onStartTour} />}
      {onSwitchToTrainer && (
        <Section footer="Ваше расписание и клиенты остаются в профиле тренера.">
          <Row
            title="Профиль тренера"
            icon={{ name: 'user', color: 'var(--c-violet)' }}
            chevron
            onClick={onSwitchToTrainer}
          />
        </Section>
      )}
      <PrivacySection trainer={onSwitchToTrainer !== undefined} />
      {rulesOf && <RulesScreen trainer={rulesOf} onBack={() => setRulesOf(null)} />}
    </>
  )
}
