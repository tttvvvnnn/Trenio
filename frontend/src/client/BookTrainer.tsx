import { useEffect, useState } from 'react'

import {
  errorText,
  createMyBooking,
  fetchMyBookingsFor,
  fetchMyPackages,
  fetchTrainerServices,
  fetchTrainerSlots,
  type Booking,
  type ClientTrainer,
  type Package,
  type Service,
  type Slot,
} from '../api'
import { clientTone, monthDays, type Tone } from '../calendar'
import {
  BOOKING_STATUS,
  ATTENDANCE_SHORT,
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
import { Chips, EmptyState, ErrorText, Row, SkeletonList } from '../ui/kit'
import MonthGrid from '../ui/MonthGrid'
import { MainButton } from '../ui/native'
import { useRefreshKey } from '../sync'
import RepeatCard from './RepeatCard'

// Цвет плашки своей записи в списке дня
const TONE_COLOR: Record<Tone, string> = {
  planned: 'var(--c-planned)',
  pending: 'var(--c-warning)',
  alert: 'var(--c-alert)',
  done: 'var(--c-success)',
  missed: 'var(--c-hint)',
  unmarked: 'var(--c-violet)',
}

type Props = {
  trainer: ClientTrainer
  onBooked: (booking: Booking) => void
}

/** Запись к одному тренеру: услуга → день → время → «Записаться». */
export default function BookTrainer({ trainer, onBooked }: Props) {
  const [services, setServices] = useState<Service[] | null>(null)
  const [serviceId, setServiceId] = useState<number | null>(null)
  const today = localDate(new Date(), trainer.timezone)
  const [month, setMonth] = useState(`${today.slice(0, 7)}-01`)
  // Окошки и свои записи загружены для month; null — ещё грузятся
  const [slots, setSlots] = useState<{ month: string; items: Slot[] } | null>(null)
  const [mine, setMine] = useState<{ month: string; items: Booking[] } | null>(null)
  const [selectedDay, setSelectedDay] = useState<string | null>(null)
  const [selected, setSelected] = useState<Slot | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [packages, setPackages] = useState<Package[]>([])

  useEffect(() => {
    fetchTrainerServices(trainer.id)
      .then((loaded) => {
        setServices(loaded)
        setServiceId(loaded[0]?.id ?? null)
      })
      .catch((err: unknown) => setError(errorText(err)))
  }, [trainer.id])

  // Увеличиваем, чтобы перечитать окошки
  const [reloads, setReloads] = useState(0)
  const refreshKey = useRefreshKey()

  useEffect(() => {
    if (serviceId === null) return
    let stale = false
    const days = monthDays(month)
    const last = days[days.length - 1]
    // В прошлое не записывают: окошки нужны с сегодняшнего дня
    const first = days[0] > today ? days[0] : today
    if (first > last) {
      setSlots({ month, items: [] })
      return
    }
    const count = Math.round((Date.parse(last) - Date.parse(first)) / 86_400_000) + 1
    fetchTrainerSlots(trainer.id, serviceId, count, first)
      .then((loaded) => {
        if (!stale) setSlots({ month, items: loaded })
      })
      .catch((err: unknown) => setError(errorText(err)))
    return () => {
      stale = true
    }
  }, [trainer.id, serviceId, month, today, reloads, refreshKey])

  // Другая услуга или месяц: выбранное время больше не подходит
  useEffect(() => {
    setSelected(null)
  }, [serviceId, month])

  useEffect(() => {
    let stale = false
    const days = monthDays(month)
    fetchMyBookingsFor(trainer.id, days[0], days.length)
      .then((loaded) => {
        if (!stale) setMine({ month, items: loaded })
      })
      .catch((err: unknown) => setError(errorText(err)))
    return () => {
      stale = true
    }
  }, [trainer.id, month, reloads, refreshKey])

  useEffect(() => {
    // Блоки нужны только для подсказки: без них запись всё равно работает
    fetchMyPackages()
      .then((loaded) => setPackages(loaded.filter((pkg) => pkg.trainer.id === trainer.id)))
      .catch(() => setPackages([]))
  }, [trainer.id, reloads, refreshKey])

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
      setError(errorText(err))
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
  const loading = slots?.month !== month || mine?.month !== month
  const byDay = new Map<string, Slot[]>()
  for (const slot of slots?.month === month ? slots.items : []) {
    const day = localDate(slot.starts_at, timezone)
    byDay.set(day, [...(byDay.get(day) ?? []), slot])
  }
  const mineByDay = new Map<string, Booking[]>()
  // Отменённые и отклонённые в календаре не показываем, они есть в «Моих занятиях»
  for (const booking of mine?.month === month ? mine.items : []) {
    if (booking.attendance === null && !['pending', 'confirmed'].includes(booking.status)) continue
    const day = localDate(booking.starts_at, timezone)
    mineByDay.set(day, [...(mineByDay.get(day) ?? []), booking])
  }
  const now = new Date()
  // По умолчанию открыт сегодняшний или ближайший день со свободным временем
  const firstFree = monthDays(month).find(
    (day) => day.slice(0, 7) === month.slice(0, 7) && byDay.has(day),
  )
  const current =
    selectedDay ?? (byDay.has(today) || mineByDay.has(today) ? today : (firstFree ?? today))
  const daySlots = byDay.get(current) ?? []
  const dayMine = mineByDay.get(current) ?? []

  // Выбранное время не покрыто блоком: запись будет разовой
  const oneOff =
    selected !== null && !covered(packages, service.id, localDate(selected.starts_at, timezone))
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
      <RepeatCard key={reloads} trainer={trainer} onBooked={onBooked} />
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
      <MonthGrid
        month={month}
        today={today}
        isSelected={(day) => day === current}
        loading={loading}
        compact
        onMonth={(next) => {
          setMonth(next)
          setSelectedDay(null)
          setSelected(null)
        }}
        onSelect={(day) => {
          setSelectedDay(day)
          setSelected(null)
        }}
        dayClass={(day) => (byDay.has(day) ? 'free' : mineByDay.has(day) ? undefined : 'empty')}
        dayLabel={(day) => {
          const own = mineByDay.get(day)?.length ?? 0
          const free = byDay.get(day)?.length ?? 0
          return `${dayTitle(day)}: ${own > 0 ? `моих записей ${own}, ` : ''}${free > 0 ? 'есть свободное время' : 'нет свободного времени'}`
        }}
        renderDay={(day) => (
          <>
            {(mineByDay.get(day) ?? []).slice(0, 2).map((booking) => (
              <span key={booking.id} className={`month-chip ${clientTone(booking, now)}`}>
                <b>{localTime(booking.starts_at, timezone)}</b>
              </span>
            ))}
            {byDay.has(day) && !mineByDay.has(day) && <i className="month-free" />}
          </>
        )}
        legend={
          <>
            <span>
              <i className="month-free" />
              есть время
            </span>
            <span>
              <i className="month-dot month-tag planned" />
              моя запись
            </span>
            <span>
              <i className="month-dot month-tag done" />
              прошла
            </span>
            <span>
              <i className="month-dot month-tag missed" />
              пропуск или без отметки
            </span>
          </>
        }
      />
      <h2 className="section-title day-title">{dayTitle(current)}</h2>
      {dayMine.length > 0 && (
        <div className="group">
          {dayMine.map((booking) => (
            <Row
              key={booking.id}
              title={`${localTime(booking.starts_at, timezone)} · ${booking.service.name}`}
              subtitle={
                booking.attendance
                  ? ATTENDANCE_SHORT[booking.attendance]
                  : new Date(booking.starts_at) <= now
                    ? 'тренер ещё не отметил'
                    : BOOKING_STATUS[booking.status].toLowerCase()
              }
              icon={{
                name: booking.attendance === 'attended' ? 'check' : 'calendar',
                color: TONE_COLOR[clientTone(booking, now)],
              }}
            />
          ))}
        </div>
      )}
      {!loading && daySlots.length === 0 && dayMine.length === 0 && (
        <p className="section-footer">
          {current < today ? 'Этот день уже прошёл.' : 'В этот день свободного времени нет.'}
        </p>
      )}
      {daySlots.length > 0 && (
        <section className="section">
          <h2 className="section-title">Свободное время</h2>
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
        </section>
      )}
      {error && <ErrorText>{error}</ErrorText>}
      {selected && oneOff && trainer.one_off_mode === 'forbid' && (
        <p className="section-footer hint-alert">
          Тренер записывает только по блоку, а свободного занятия в блоке на этот день у вас нет.
          Купите блок у тренера, чтобы записаться.
        </p>
      )}
      {selected && oneOff && trainer.one_off_mode === 'confirm' && (
        <p className="section-footer hint-alert">
          Эта запись будет без блока, поэтому её подтвердит тренер. Об оплате договоритесь с ним.
        </p>
      )}
      {selected && oneOff && trainer.one_off_mode === 'allow' && packages.length > 0 && (
        <p className="section-footer hint-alert">
          Занятия в вашем блоке закончились или уже заняты записями. Эта запись будет без блока: об
          оплате договоритесь с тренером.
        </p>
      )}
      <p className="section-footer">{rules.join(' ')}</p>
      <MainButton
        text={selected ? `Записаться: ${dateTime(selected.starts_at, timezone)}` : 'Записаться'}
        onClick={() => void book()}
        visible={selected !== null}
        disabled={oneOff && trainer.one_off_mode === 'forbid'}
        loading={saving}
      />
    </>
  )
}

// Хватит ли блока на ещё одну запись
function covered(packages: Package[], serviceId: number, day: string): boolean {
  return packages.some(
    (pkg) =>
      pkg.status === 'active' &&
      (pkg.service === null || pkg.service.id === serviceId) &&
      (pkg.valid_until === null || pkg.valid_until >= day) &&
      pkg.left - pkg.planned.length > 0,
  )
}
