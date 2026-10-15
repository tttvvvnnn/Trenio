import { useState } from 'react'

import type { ProgressPoint, ProgressSeries } from '../api'
import { longDate, measure, shortDate } from '../format'
import { Row, Section } from './kit'

// Изменение от первого замера: "−3,1 кг с 01.01"
function change(series: ProgressSeries): string | null {
  const { points } = series
  if (points.length < 2) return null
  const delta = Math.round((points[points.length - 1].value - points[0].value) * 100) / 100
  if (delta === 0) return `без изменений с ${shortDate(points[0].day)}`
  const sign = delta > 0 ? '+' : '−'
  return `${sign}${measure(Math.abs(delta), series.unit)} с ${shortDate(points[0].day)}`
}

/** Маленький график без осей: видно, куда идёт значение. */
function Sparkline({ points }: { points: ProgressPoint[] }) {
  if (points.length < 2) return null
  const values = points.map((point) => point.value)
  const min = Math.min(...values)
  const span = Math.max(...values) - min || 1
  const coords = values.map((value, index) => {
    const x = (index / (values.length - 1)) * 100
    const y = 28 - ((value - min) / span) * 24
    return [x, y] as const
  })
  return (
    <svg className="sparkline" viewBox="-3 0 106 32" preserveAspectRatio="none" aria-hidden="true">
      <polyline points={coords.map(([x, y]) => `${x},${y}`).join(' ')} />
    </svg>
  )
}

type Props = {
  series: ProgressSeries[]
  // Тренер может удалить ошибочный замер; клиент только смотрит
  onPick?: (point: ProgressPoint, series: ProgressSeries) => void
}

/** Замеры по видам: последнее значение, изменение, график и все замеры. */
export default function ProgressList({ series, onPick }: Props) {
  return (
    <>
      {series.map((item) => (
        <SeriesSection key={item.key} series={item} onPick={onPick} />
      ))}
    </>
  )
}

// Столько последних замеров видно сразу, остальные — по кнопке
const POINTS_SHOWN = 5

function SeriesSection({ series, onPick }: { series: ProgressSeries } & Pick<Props, 'onPick'>) {
  const [all, setAll] = useState(false)
  const last = series.points[series.points.length - 1]
  const delta = change(series)
  const newest = [...series.points].reverse()
  const shown = all ? newest : newest.slice(0, POINTS_SHOWN)
  return (
    <Section title={series.label}>
      <div className="progress-head">
        <div className="progress-now">
          <strong>{measure(last.value, series.unit)}</strong>
          <span>{delta ?? `замер ${shortDate(last.day)}`}</span>
        </div>
        <Sparkline points={series.points} />
      </div>
      {shown.map((point) => (
        <Row
          key={point.id}
          title={longDate(point.day)}
          value={measure(point.value, series.unit)}
          onClick={onPick ? () => onPick(point, series) : undefined}
        />
      ))}
      {shown.length < newest.length && (
        <Row title={`Все замеры: ${newest.length}`} tone="accent" onClick={() => setAll(true)} />
      )}
    </Section>
  )
}
