import { useState } from 'react'

import { setBookingTerms, type Booking } from '../api'
import { bookingMinutes, parsePrice } from '../format'
import { haptic } from '../telegram'
import { ErrorText } from '../ui/kit'
import { MainButton } from '../ui/native'
import Screen from '../ui/Screen'
import TermsFields, { type TermsValue } from './TermsFields'

type Props = {
  booking: Booking
  onBack: () => void
  onSaved: (booking: Booking) => void
}

/** Тренер меняет условия одного занятия. */
export default function BookingTerms({ booking, onBack, onSaved }: Props) {
  const initial: TermsValue = {
    durationMin: bookingMinutes(booking),
    price: booking.price === null ? '' : String(booking.price),
    noPackage: booking.no_package,
  }
  const [terms, setTerms] = useState(initial)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const active = booking.status === 'pending' || booking.status === 'confirmed'
  const durationLocked = !active || Date.parse(booking.starts_at) <= Date.now()
  const price = parsePrice(terms.price)
  const changed =
    terms.durationMin !== initial.durationMin ||
    (price !== null && price !== booking.price) ||
    terms.noPackage !== initial.noPackage

  async function save() {
    if (!changed || saving) return
    setSaving(true)
    setError(null)
    try {
      const updated = await setBookingTerms(booking.id, {
        duration_min: terms.durationMin !== initial.durationMin ? terms.durationMin : undefined,
        price: price !== null && price !== booking.price ? price : undefined,
        no_package: terms.noPackage !== initial.noPackage ? terms.noPackage : undefined,
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
    <Screen title="Условия занятия" subtitle={booking.service.name} onBack={onBack}>
      <TermsFields
        value={terms}
        onChange={setTerms}
        group={booking.service.capacity > 1}
        durationLocked={durationLocked}
        footer="Меняется только это занятие. Цена считается в финансах, если занятие разовое; из блока занятие стоит долю блока."
      />
      {error && <ErrorText>{error}</ErrorText>}
      <MainButton
        text="Сохранить"
        onClick={() => void save()}
        disabled={!changed}
        loading={saving}
      />
    </Screen>
  )
}
