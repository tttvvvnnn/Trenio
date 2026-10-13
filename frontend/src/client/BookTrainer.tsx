import { useEffect, useState } from 'react'

import {
  createMyBooking,
  fetchTrainerServices,
  fetchTrainerSlots,
  type Booking,
  type ClientTrainer,
  type Service,
  type Slot,
} from '../api'
import {
  addDays,
  dateTime,
  dayTitle,
  deviceTimezone,
  duration,
  localDate,
  localTime,
  plural,
  rubles,
} from '../format'
import { haptic } from '../telegram'
import DateStrip from '../ui/DateStrip'
import { Chips, EmptyState, ErrorText, SkeletonList } from '../ui/kit'
import { MainButton } from '../ui/native'

// Сколько дней вперёд клиент видит окошки
const DAYS = 14

type Props = {
  trainer: ClientTrainer
  onBooked: (booking: Booking) => void
}

/** Запись к одному тренеру: услуга → день → время → «Записаться». */
export default function BookTrainer({ trainer, onBooked }: Props) {
  const [services, setServices] = useState<Service[] | null>(null)
  const [serviceId, setServiceId] = useState<number | null>(null)
  const [slots, setSlots] = useState<Slot[] | null>(null)
  const [selectedDay, setSelectedDay] = useState<string | null>(null)
  const [selected, setSelected] = useState<Slot | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    fetchTrainerServices(trainer.id)
      .then((loaded) => {
        setServices(loaded)
        setServiceId(loaded[0]?.id ?? null)
      })
      .catch((err: unknown) => setError(String(err)))
  }, [trainer.id])

  // Увеличиваем, чтобы перечитать окошки
  const [reloads, setReloads] = useState(0)

  useEffect(() => {
    if (serviceId === null) return
    let stale = false
    setSlots(null)
    setSelected(null)
    fetchTrainerSlots(trainer.id, serviceId, DAYS)
      .then((loaded) => {
        if (!stale) setSlots(loaded)
      })
      .catch((err: unknown) => setError(String(err)))
    return () => {
      stale = true
    }
  }, [trainer.id, serviceId, reloads])

  async function book() {
    if (selected === null || saving) return
    setSaving(true)
    setError(null)
    try {
      const booking = await createMyBooking({
        trainer_id: trainer.id,
        service_id: selected.service_id,
        starts_at: selected.starts_at,
      })
      haptic.success()
      // Сбрасываем выбор: занятое окошко пропадёт из списка
      setReloads((count) => count + 1)
      onBooked(booking)
    } catch (err) {
      haptic.error()
      setError(err instanceof Error ? err.message : String(err))
      // Окошко могли занять, пока клиент выбирал: показываем свежие
      setReloads((count) => count + 1)
    } finally {
      setSaving(false)
    }
  }

  if (services === null) {
    return error ? <ErrorText>{error}</ErrorText> : <SkeletonList rows={2} />
  }
  if (services.length === 0) {
    return (
      <EmptyState
        icon="calendar"
        title="Записи пока нет"
        text="Тренер ещё не настроил услуги. Загляните позже."
      />
    )
  }

  const timezone = trainer.timezone
  const service = services.find((item) => item.id === serviceId) ?? services[0]
  const byDay = new Map<string, Slot[]>()
  for (const slot of slots ?? []) {
    const day = localDate(slot.starts_at, timezone)
    byDay.set(day, [...(byDay.get(day) ?? []), slot])
  }
  const today = localDate(new Date(), timezone)
  const days = Array.from({ length: DAYS }, (_, index) => addDays(today, index))
  // По умолчанию открыт ближайший день со свободным временем
  const current = selectedDay ?? days.find((day) => byDay.has(day)) ?? today
  const daySlots = byDay.get(current) ?? []

  const rules = [
    trainer.auto_confirm ? 'Запись подтверждается сразу.' : 'Запись подтверждает тренер.',
    trainer.cancel_hours > 0
      ? `Отменить самому можно не позже чем за ${trainer.cancel_hours} ч до начала.`
      : 'Отменить самому можно в любой момент до начала.',
  ]
  if (timezone !== deviceTimezone()) {
    rules.push(`Время указано по часовому поясу тренера (${timezone}).`)
  }

  return (
    <>
      {services.length > 1 && (
        <section className="section">
          <h2 className="section-title">Услуга</h2>
          <Chips
            label="Услуга"
            value={service.id}
            options={services.map((item) => [item.id, item.name] as const)}
            onChange={(id) => {
              setSelectedDay(null)
              setServiceId(id)
            }}
          />
        </section>
      )}
      <div className="group service-card">
        <div className="service-head">
          <strong>{service.name}</strong>
          <span>
            {duration(service.duration_min)}
            {service.capacity > 1 && ` · до ${service.capacity} чел.`}
            {service.price !== null && ` · ${rubles(service.price)}`}
          </span>
        </div>
        {service.address && <p className="service-note">{service.address}</p>}
      </div>
      {slots === null ? (
        error ? (
          <ErrorText>{error}</ErrorText>
        ) : (
          <SkeletonList rows={1} />
        )
      ) : slots.length === 0 ? (
        <EmptyState
          icon="calendar"
          title="Свободного времени нет"
          text="На ближайшие две недели всё занято. Загляните позже или напишите тренеру."
        />
      ) : (
        <>
          <DateStrip
            days={days}
            current={current}
            count={(day) => byDay.get(day)?.length ?? 0}
            onSelect={(day) => {
              setSelectedDay(day)
              setSelected(null)
            }}
          />
          <h2 className="section-title day-title">{dayTitle(current)}</h2>
          {daySlots.length === 0 ? (
            <p className="section-footer">В этот день свободного времени нет.</p>
          ) : (
            <div className="group">
              <div className="times" role="radiogroup" aria-label="Время">
                {daySlots.map((slot) => (
                  <button
                    key={slot.starts_at}
                    type="button"
                    role="radio"
                    className="time"
                    aria-checked={selected?.starts_at === slot.starts_at}
                    onClick={() => {
                      haptic.select()
                      setSelected(slot)
                    }}
                  >
                    {localTime(slot.starts_at, timezone)}
                    {service.capacity > 1 && (
                      <small>{plural(slot.seats_left, 'место', 'места', 'мест')}</small>
                    )}
                  </button>
                ))}
              </div>
            </div>
          )}
          {error && <ErrorText>{error}</ErrorText>}
          <p className="section-footer">{rules.join(' ')}</p>
        </>
      )}
      <MainButton
        text={selected ? `Записаться: ${dateTime(selected.starts_at, timezone)}` : 'Записаться'}
        onClick={() => void book()}
        visible={selected !== null}
        loading={saving}
      />
    </>
  )
}
