import { useEffect, useState, type FormEvent } from 'react'

import { createService, fetchServices, updateService, type Service } from '../api'
import { duration, rubles } from '../format'

type Props = {
  onChanged?: () => void
}

export default function Services({ onChanged }: Props) {
  const [services, setServices] = useState<Service[] | null>(null)
  // null — форма закрыта, 'new' — новая услуга, иначе редактируем эту
  const [editing, setEditing] = useState<Service | 'new' | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function reload() {
    try {
      setServices(await fetchServices(true))
    } catch (err) {
      setError(String(err))
    }
  }

  useEffect(() => {
    void reload()
  }, [])

  async function toggle(service: Service) {
    await updateService(service.id, { is_active: !service.is_active })
    await reload()
    onChanged?.()
  }

  if (services === null) {
    return <p className="hint">{error ?? 'Загрузка…'}</p>
  }

  if (editing !== null) {
    return (
      <ServiceForm
        service={editing === 'new' ? null : editing}
        onDone={async () => {
          setEditing(null)
          await reload()
          onChanged?.()
        }}
        onCancel={() => setEditing(null)}
      />
    )
  }

  return (
    <section>
      {services.length === 0 && (
        <p className="hint">
          Добавьте услуги, на которые клиенты будут записываться: например, «Персональная, 60 мин».
        </p>
      )}
      <ul className="list">
        {services.map((service) => (
          <li key={service.id} className={service.is_active ? 'card' : 'card muted'}>
            <div className="card-title">{service.name}</div>
            <div className="hint">
              {duration(service.duration_min)}
              {service.capacity > 1 ? ` · до ${service.capacity} человек` : ' · индивидуально'}
              {service.price !== null ? ` · ${rubles(service.price)}` : ''}
              {service.address ? ` · ${service.address}` : ''}
              {!service.is_active && ' · выключена'}
            </div>
            <div className="actions">
              <button type="button" className="link" onClick={() => setEditing(service)}>
                Изменить
              </button>
              <button type="button" className="link" onClick={() => void toggle(service)}>
                {service.is_active ? 'Выключить' : 'Включить'}
              </button>
            </div>
          </li>
        ))}
      </ul>
      <button type="button" onClick={() => setEditing('new')}>
        Добавить услугу
      </button>
    </section>
  )
}

type FormProps = {
  service: Service | null
  onDone: () => void
  onCancel: () => void
}

function ServiceForm({ service, onDone, onCancel }: FormProps) {
  const [name, setName] = useState(service?.name ?? '')
  const [durationMin, setDurationMin] = useState(String(service?.duration_min ?? 60))
  const [capacity, setCapacity] = useState(String(service?.capacity ?? 1))
  const [price, setPrice] = useState(service?.price != null ? String(service.price) : '')
  const [address, setAddress] = useState(service?.address ?? '')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    const data = {
      name: name.trim(),
      duration_min: Number(durationMin),
      capacity: Number(capacity),
      price: price.trim() === '' ? null : Number(price),
      address: address.trim() || null,
    }
    try {
      if (service === null) {
        await createService(data)
      } else {
        // Пустая строка очищает адрес услуги, тогда берётся адрес тренера
        await updateService(service.id, { ...data, address: data.address ?? '' })
      }
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setSaving(false)
    }
  }

  return (
    <form className="form" onSubmit={submit}>
      <h2>{service === null ? 'Новая услуга' : 'Услуга'}</h2>
      <label>
        Название
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Персональная тренировка"
          maxLength={128}
          required
        />
      </label>
      <label>
        Длительность, минут
        <input
          type="number"
          min={5}
          max={600}
          step={5}
          value={durationMin}
          onChange={(event) => setDurationMin(event.target.value)}
          required
        />
      </label>
      <label>
        Сколько человек одновременно
        <input
          type="number"
          min={1}
          max={100}
          value={capacity}
          onChange={(event) => setCapacity(event.target.value)}
          required
        />
      </label>
      <label>
        Цена разового занятия, ₽ (необязательно)
        <input
          type="number"
          min={0}
          value={price}
          onChange={(event) => setPrice(event.target.value)}
        />
      </label>
      <label>
        Место (если отличается от адреса зала)
        <input
          value={address}
          onChange={(event) => setAddress(event.target.value)}
          maxLength={256}
        />
      </label>
      {error && <p className="error">{error}</p>}
      <div className="actions">
        <button type="submit" disabled={saving}>
          Сохранить
        </button>
        <button type="button" className="secondary" onClick={onCancel}>
          Отмена
        </button>
      </div>
    </form>
  )
}
