import { useState } from 'react'

import {
  addManualSession,
  addPayment,
  deleteManualSession,
  deletePackage,
  deletePayment,
  fetchTrainerBooking,
  updateManualSession,
  updatePackage,
  type Booking,
  type Package,
  type PackageSession,
  type Payment,
} from '../api'
import { localDate, longDate, rubles, shortDate } from '../format'
import { confirmAction, haptic } from '../telegram'
import { AddRow, Chips, ErrorText, InlineField, Row, Section } from '../ui/kit'
import { MainButton } from '../ui/native'
import PackageSummary from '../ui/PackageSummary'
import Screen from '../ui/Screen'
import BookingDetails from './BookingDetails'

type Props = {
  pkg: Package
  clientName: string
  timezone: string
  onBack: () => void
  // null — блок удалён
  onChanged: (pkg: Package | null) => void
}

/** Блок глазами тренера: деньги, занятия и действия с ними. */
export default function PackageDetails({ pkg, clientName, timezone, onBack, onChanged }: Props) {
  const [form, setForm] = useState<'payment' | 'session' | PackageSession | null>(null)
  const [booking, setBooking] = useState<Booking | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function run(action: () => Promise<Package | null>) {
    setBusy(true)
    setError(null)
    try {
      const updated = await action()
      haptic.success()
      onChanged(updated)
    } catch (err) {
      haptic.error()
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  async function openBooking(id: number) {
    setError(null)
    try {
      setBooking(await fetchTrainerBooking(id))
    } catch (err) {
      haptic.error()
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  function openSession(session: PackageSession) {
    if (session.booking_id === null) setForm(session)
    else void openBooking(session.booking_id)
  }

  async function removePayment(payment: Payment) {
    const ok = await confirmAction(
      `Удалить платёж ${rubles(payment.amount)} от ${shortDate(payment.paid_on)}?`,
      'Удалить',
    )
    if (ok) void run(() => deletePayment(pkg.id, payment.id))
  }

  async function remove() {
    const ok = await confirmAction('Удалить блок вместе с платежами?', 'Удалить')
    if (ok) void run(() => deletePackage(pkg.id).then(() => null))
  }

  const closed = pkg.status === 'closed'
  return (
    <Screen title={pkg.name} subtitle={clientName} onBack={onBack}>
      <PackageSummary
        pkg={pkg}
        onSession={openSession}
        onPlanned={(planned) => void openBooking(planned.booking_id)}
        onFree={pkg.left > 0 && !closed ? () => setForm('session') : undefined}
      />
      <Section title="Платежи" footer="Это только учёт: деньги через бот не проходят.">
        {pkg.payments.map((payment) => (
          <Row
            key={payment.id}
            title={rubles(payment.amount)}
            subtitle={payment.comment ?? undefined}
            value={longDate(payment.paid_on)}
            onClick={busy ? undefined : () => void removePayment(payment)}
          />
        ))}
        <AddRow title="Внести платёж" onClick={() => setForm('payment')} />
      </Section>
      <Section footer="Нажмите на занятие: по записи откроется сама запись, где ставится отметка. Свободное занятие можно отметить без записи, если оно прошло вне Trenio.">
        <Row
          title={closed ? 'Открыть блок снова' : 'Закрыть блок досрочно'}
          tone="accent"
          onClick={
            busy ? undefined : () => void run(() => updatePackage(pkg.id, { closed: !closed }))
          }
        />
      </Section>
      {pkg.used === 0 && (
        <Section>
          <Row
            title="Удалить блок"
            tone="destructive"
            onClick={busy ? undefined : () => void remove()}
          />
        </Section>
      )}
      {error && <ErrorText>{error}</ErrorText>}
      {form === 'payment' && (
        <PaymentForm
          pkg={pkg}
          today={localDate(new Date(), timezone)}
          onBack={() => setForm(null)}
          onSaved={(updated) => {
            setForm(null)
            onChanged(updated)
          }}
        />
      )}
      {(form === 'session' || (typeof form === 'object' && form !== null)) && (
        <SessionForm
          pkg={pkg}
          session={form === 'session' ? null : form}
          today={localDate(new Date(), timezone)}
          onBack={() => setForm(null)}
          onSaved={(updated) => {
            setForm(null)
            onChanged(updated)
          }}
        />
      )}
      {booking && (
        <BookingDetails
          booking={booking}
          onBack={() => setBooking(null)}
          onChanged={(updated) => {
            setBooking(updated)
            onChanged(pkg)
          }}
        />
      )}
    </Screen>
  )
}

type FormProps = {
  pkg: Package
  today: string
  onBack: () => void
  onSaved: (pkg: Package) => void
}

function PaymentForm({ pkg, today, onBack, onSaved }: FormProps) {
  const [amount, setAmount] = useState(pkg.due > 0 ? String(pkg.due) : '')
  const [day, setDay] = useState(today)
  const [comment, setComment] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const value = Number(amount.replace(/\s/g, ''))
  const valid = value > 0 && day !== ''

  async function submit() {
    if (!valid || saving) return
    setSaving(true)
    setError(null)
    try {
      const updated = await addPayment(pkg.id, {
        amount: value,
        paid_on: day,
        comment: comment.trim() || null,
      })
      haptic.success()
      onSaved(updated)
    } catch (err) {
      haptic.error()
      setError(err instanceof Error ? err.message : String(err))
      setSaving(false)
    }
  }

  return (
    <Screen title="Платёж" subtitle={pkg.name} onBack={onBack}>
      <Section
        footer={pkg.due > 0 ? `Осталось доплатить ${rubles(pkg.due)}.` : 'Блок уже оплачен.'}
      >
        <InlineField label="Сумма, ₽">
          {(id) => (
            <input
              id={id}
              className="row-input"
              inputMode="numeric"
              placeholder="0"
              value={amount}
              onChange={(event) => setAmount(event.target.value.replace(/[^\d\s]/g, ''))}
            />
          )}
        </InlineField>
        <InlineField label="Дата">
          {(id) => (
            <input
              id={id}
              className="row-input"
              type="date"
              value={day}
              onChange={(event) => setDay(event.target.value)}
            />
          )}
        </InlineField>
        <InlineField label="Комментарий">
          {(id) => (
            <input
              id={id}
              className="row-input"
              placeholder="наличные, перевод…"
              maxLength={256}
              value={comment}
              onChange={(event) => setComment(event.target.value)}
            />
          )}
        </InlineField>
      </Section>
      {error && <ErrorText>{error}</ErrorText>}
      <MainButton text="Внести" onClick={() => void submit()} disabled={!valid} loading={saving} />
    </Screen>
  )
}

function SessionForm({
  pkg,
  session,
  today,
  onBack,
  onSaved,
}: FormProps & { session: PackageSession | null }) {
  const [day, setDay] = useState(session?.day ?? today)
  const [attendance, setAttendance] = useState<'attended' | 'missed_charged'>(
    session?.status ?? 'attended',
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function save(action: () => Promise<Package>) {
    setSaving(true)
    setError(null)
    try {
      const updated = await action()
      haptic.success()
      onSaved(updated)
    } catch (err) {
      haptic.error()
      setError(err instanceof Error ? err.message : String(err))
      setSaving(false)
    }
  }

  function submit() {
    if (day === '' || saving) return
    void save(() =>
      session === null
        ? addManualSession(pkg.id, { day, attendance })
        : updateManualSession(pkg.id, session.id, { day, attendance }),
    )
  }

  async function remove() {
    if (session === null) return
    const ok = await confirmAction(
      `Снять занятие ${session.number} от ${shortDate(session.day)}? Оно вернётся в блок.`,
      'Снять',
    )
    if (ok) void save(() => deleteManualSession(pkg.id, session.id))
  }

  return (
    <Screen
      title={session === null ? 'Занятие без записи' : `Занятие ${session.number}`}
      subtitle={pkg.name}
      onBack={onBack}
    >
      <Section
        footer={
          session === null
            ? `Спишется занятие ${pkg.used + 1} из ${pkg.sessions_count}. Так отмечают занятия, на которые не было записи в Trenio.`
            : 'Отмечено в блоке вручную, без записи.'
        }
      >
        <Chips
          label="Отметка"
          value={attendance}
          options={[
            ['attended', 'Прошла'],
            ['missed_charged', 'Пропуск, списать'],
          ]}
          onChange={setAttendance}
        />
        <InlineField label="Дата">
          {(id) => (
            <input
              id={id}
              className="row-input"
              type="date"
              value={day}
              onChange={(event) => setDay(event.target.value)}
            />
          )}
        </InlineField>
      </Section>
      {session !== null && (
        <Section>
          <Row
            title="Снять занятие"
            tone="destructive"
            onClick={saving ? undefined : () => void remove()}
          />
        </Section>
      )}
      {error && <ErrorText>{error}</ErrorText>}
      <MainButton
        text={session === null ? 'Списать' : 'Сохранить'}
        onClick={submit}
        disabled={day === ''}
        loading={saving}
      />
    </Screen>
  )
}
