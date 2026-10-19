import { useEffect, useState } from 'react'

import {
  errorText,
  fetchAdminPromo,
  saveAdminPromo,
  type AdminPromo,
  type PromoSettings,
} from '../api'
import { haptic } from '../telegram'
import { ErrorText, Row, Section, SkeletonList, Stepper, SwitchRow, TextField } from '../ui/kit'
import { MainButton } from '../ui/native'
import { PromoScreen } from '../ui/Promo'
import Screen from '../ui/Screen'

// Через сколько дней после первого входа показать карточку на главном
const DELAYS = [0, 1, 2, 3, 5, 7, 14, 30]

/** Промо от автора: тексты, промокод, ссылка и сколько людей до него дошло. */
export default function AdminPromo({ onBack }: { onBack: () => void }) {
  const [data, setData] = useState<AdminPromo | null>(null)
  const [form, setForm] = useState<PromoSettings | null>(null)
  const [preview, setPreview] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchAdminPromo()
      .then((loaded) => {
        setData(loaded)
        setForm(loaded.settings)
      })
      .catch((err: unknown) => setError(errorText(err)))
  }, [])

  function set<K extends keyof PromoSettings>(key: K, value: PromoSettings[K]) {
    setForm((current) => (current ? { ...current, [key]: value } : current))
  }

  async function save() {
    if (form === null) return
    setSaving(true)
    setError(null)
    try {
      const saved = await saveAdminPromo(form)
      haptic.success()
      setData(saved)
      setForm(saved.settings)
    } catch (err) {
      haptic.error()
      setError(errorText(err))
    } finally {
      setSaving(false)
    }
  }

  const dirty =
    data !== null && form !== null && JSON.stringify(data.settings) !== JSON.stringify(form)

  return (
    <Screen
      title="Промо от автора"
      subtitle="Карточка на главном экране и строка в Профиле у тренеров и клиентов"
      onBack={onBack}
    >
      {error && <ErrorText>{error}</ErrorText>}
      {form === null && !error && <SkeletonList rows={4} />}
      {data && form && (
        <>
          <Section footer="Выключили — карточка и строка в Профиле пропадут у всех сразу.">
            <SwitchRow
              label="Показывать"
              checked={form.enabled}
              onChange={(value) => set('enabled', value)}
            />
            <Row
              title="Карточка на главном"
              subtitle="Через сколько дней после первого входа"
              after={
                <Stepper
                  label="Дней после первого входа"
                  value={form.delay_days}
                  options={DELAYS}
                  onChange={(value) => set('delay_days', value)}
                  format={(value) => `${value} дн`}
                />
              }
            />
            <Row title="Посмотреть экран с кодом" chevron onClick={() => setPreview(true)} />
          </Section>
          <Section
            title="Сколько людей"
            footer="Каждый человек считается один раз. Открыли код — из карточки или из Профиля."
          >
            <Row title="Увидели карточку" value={String(data.stats.shown)} />
            <Row title="Закрыли крестиком" value={String(data.stats.dismissed)} />
            <Row title="Открыли код" value={String(data.stats.claimed)} />
            <Row title={`Нажали «${data.settings.button}»`} value={String(data.stats.opened)} />
          </Section>
          <TextField
            label="Заголовок"
            value={form.title}
            maxLength={80}
            onChange={(value) => set('title', value)}
          />
          <TextField
            label="Строка под заголовком в карточке"
            value={form.subtitle}
            maxLength={160}
            onChange={(value) => set('subtitle', value)}
          />
          <section className="section">
            <h2 className="section-title">Описание на экране с кодом</h2>
            <div className="group">
              <textarea
                className="field-input rules-input"
                aria-label="Описание на экране с кодом"
                maxLength={600}
                value={form.text}
                onChange={(event) => set('text', event.target.value)}
              />
            </div>
          </section>
          <TextField
            label="Промокод"
            value={form.code}
            maxLength={32}
            onChange={(value) => set('code', value.toUpperCase())}
          />
          <TextField
            label="Ссылка"
            value={form.url}
            maxLength={200}
            footer="Бот в Telegram (https://t.me/…) или сайт, начинается с https://"
            onChange={(value) => set('url', value.trim())}
          />
          <TextField
            label="Текст кнопки"
            value={form.button}
            maxLength={32}
            onChange={(value) => set('button', value)}
          />
          <MainButton
            text="Сохранить"
            onClick={() => void save()}
            visible={dirty && !preview}
            loading={saving}
          />
        </>
      )}
      {preview && form && <PromoScreen promo={form} preview onBack={() => setPreview(false)} />}
    </Screen>
  )
}
