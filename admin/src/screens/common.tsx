import type { ReactNode } from 'react'
import { avatarColor, initials } from '../format'

export type ScreenProps = { onUnauthorized: () => void }

export function Skeleton({ span = 'span-12' }: { span?: string }) {
  return <div className={`skeleton ${span}`} aria-hidden="true" />
}

export function ErrorTile({ text, onRetry }: { text: string; onRetry: () => void }) {
  return (
    <section className="glass tile span-12" role="alert">
      <h2>Не удалось загрузить данные</h2>
      <p className="muted" style={{ margin: 0 }}>
        {text}
      </p>
      <div>
        <button type="button" className="btn secondary" onClick={onRetry}>
          Повторить
        </button>
      </div>
    </section>
  )
}

export function PageTitle({ sub, title, children }: { sub: string; title: string; children?: ReactNode }) {
  return (
    <div className="page-title">
      <div>
        <span className="muted small">{sub}</span>
        <h1>{title}</h1>
      </div>
      {children}
    </div>
  )
}

export function Avatar({ id, name, url, size = 38 }: { id: number; name: string; url: string | null; size?: number }) {
  const style = { width: size, height: size, background: avatarColor(id) }
  if (url) {
    return <img className="avatar" src={url} alt="" style={style} />
  }
  return (
    <span className="avatar" aria-hidden="true" style={style}>
      {initials(name)}
    </span>
  )
}

// Столбики: высота по максимуму, пустые — серые
export function Bars({
  values,
  height,
  label,
  gap = 6,
}: {
  values: number[]
  height: number
  label: string
  gap?: number
}) {
  const max = Math.max(1, ...values)
  return (
    <div
      className="bars"
      role="img"
      aria-label={label}
      style={{ gridTemplateColumns: `repeat(${values.length}, minmax(0, 1fr))`, height, gap }}
    >
      {values.map((value, index) => (
        <span
          key={index}
          className={value ? undefined : 'empty'}
          style={{ height: `${Math.max(6, Math.round((value / max) * 100))}%` }}
        />
      ))}
    </div>
  )
}

// Линия по точкам; последние dashed точек — прогноз пунктиром
export function Line({
  values,
  dashed = 0,
  label,
  color = 'currentColor',
  height = 96,
}: {
  values: number[]
  dashed?: number
  label: string
  color?: string
  height?: number
}) {
  const width = 300
  const max = Math.max(1, ...values)
  const step = values.length > 1 ? width / (values.length - 1) : width
  const points = values.map((value, index) => [index * step, height - 6 - (value / max) * (height - 16)])
  const solid = points.slice(0, points.length - dashed)
  const future = points.slice(Math.max(0, points.length - dashed - 1))
  const path = (list: number[][]) => list.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ')
  return (
    <svg role="img" aria-label={label} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" style={{ width: '100%', height }}>
      <path d={path(solid)} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      {dashed > 0 && (
        <path d={path(future)} fill="none" stroke={color} strokeWidth="3" strokeDasharray="6 6" opacity="0.75" vectorEffect="non-scaling-stroke" />
      )}
    </svg>
  )
}
