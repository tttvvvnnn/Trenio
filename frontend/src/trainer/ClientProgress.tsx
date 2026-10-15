import { useEffect, useState } from 'react'

import {
  errorText,
  deleteMeasurement,
  fetchClientProgress,
  type Booking,
  type ProgressPoint,
  type ProgressSeries,
} from '../api'
import { dateTime, longDate, measure } from '../format'
import { confirmAction, haptic } from '../telegram'
import { AddRow, ErrorText, Row, Section, SkeletonList } from '../ui/kit'
import ProgressList from '../ui/Progress'
import MeasurementForm from './MeasurementForm'
import { useRefreshKey } from '../sync'

type Props = {
  clientId: number
  clientName: string
  timezone: string
  // Записи клиента из карточки: из них берём заметки к занятиям
  history: Booking[]
  onOpenBooking: (booking: Booking) => void
}

// Столько последних заметок показываем, остальные — в самих записях
const NOTES_SHOWN = 10

/** Вкладка «Прогресс» в карточке клиента: замеры с графиками и заметки к занятиям. */
export default function ClientProgress({
  clientId,
  clientName,
  timezone,
  history,
  onOpenBooking,
}: Props) {
  const [series, setSeries] = useState<ProgressSeries[] | null>(null)
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const refreshKey = useRefreshKey()

  useEffect(() => {
    fetchClientProgress(clientId)
      .then(setSeries)
      .catch((err: unknown) => setError(errorText(err)))
  }, [clientId, refreshKey])

  async function remove(point: ProgressPoint, item: ProgressSeries) {
    const text = `Удалить замер «${item.label}» ${measure(point.value, item.unit)} за ${longDate(point.day)}?`
    if (!(await confirmAction(text, 'Удалить'))) return
    try {
      setSeries(await deleteMeasurement(clientId, point.id))
      haptic.success()
    } catch (err) {
      haptic.error()
      setError(errorText(err))
    }
  }

  const notes = history.filter((booking) => booking.note).slice(0, NOTES_SHOWN)

  return (
    <>
      {error && <ErrorText>{error}</ErrorText>}
      {series === null && !error && <SkeletonList rows={2} />}
      {series !== null && (
        <>
          <Section
            footer={
              series.length === 0
                ? 'Вес, обхваты или своё: время в планке, пульс. Клиент видит свои замеры, но не меняет их.'
                : 'Клиент видит свои замеры в разделе «Блоки». Нажмите на замер, чтобы удалить его.'
            }
          >
            <AddRow title="Добавить замер" onClick={() => setAdding(true)} />
          </Section>
          <ProgressList series={series} onPick={(point, item) => void remove(point, item)} />
        </>
      )}
      {notes.length > 0 && (
        <Section title="Заметки к занятиям">
          {notes.map((booking) => (
            <Row
              key={booking.id}
              title={booking.note}
              subtitle={[
                dateTime(booking.starts_at, timezone),
                booking.note_private ? 'только для вас' : null,
              ]
                .filter(Boolean)
                .join(' · ')}
              onClick={() => onOpenBooking(booking)}
            />
          ))}
        </Section>
      )}
      {adding && series !== null && (
        <MeasurementForm
          clientId={clientId}
          clientName={clientName}
          timezone={timezone}
          series={series}
          onBack={() => setAdding(false)}
          onSaved={(saved) => {
            setAdding(false)
            setSeries(saved)
          }}
        />
      )}
    </>
  )
}
