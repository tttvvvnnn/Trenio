import { useEffect, useRef, useState, type ReactNode } from 'react'
import { avatarColor, initials } from '../format'
import { trainerHref } from '../route'

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

// Имя тренера ссылкой на его профиль
export function TrainerLink({ id, name }: { id: number; name: string }) {
  return (
    <a className="person-link" href={trainerHref(id)}>
      {name}
    </a>
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

// Модальное окно на <dialog>: фокус, Esc и затемнение фона даёт браузер
export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    ref.current?.showModal()
  }, [])
  return (
    <dialog ref={ref} className="dialog" aria-labelledby="modal-title" onClose={onClose}>
      <h2 id="modal-title" style={{ margin: '0 0 14px', fontSize: 20 }}>
        {title}
      </h2>
      {children}
    </dialog>
  )
}

export type Option<T extends string> = { value: T; label: string; hint?: string }

// Выпадающий список в стиле админки: кнопка-«таблетка» и меню как у действий тренера.
// Стрелки двигают выбор, Enter выбирает, Esc и клик мимо закрывают
export function Select<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: T
  options: Option<T>[]
  onChange: (value: T) => void
}) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const root = useRef<HTMLDivElement>(null)
  const current = options.find((option) => option.value === value) ?? options[0]

  useEffect(() => {
    if (!open) return
    const close = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', close)
    return () => document.removeEventListener('pointerdown', close)
  }, [open])

  const show = () => {
    setActive(Math.max(0, options.findIndex((option) => option.value === value)))
    setOpen(true)
  }
  const choose = (option: Option<T>) => {
    onChange(option.value)
    setOpen(false)
  }

  return (
    <div
      ref={root}
      className="select"
      onKeyDown={(event) => {
        if (event.key === 'Escape') setOpen(false)
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
          event.preventDefault()
          if (!open) return show()
          const step = event.key === 'ArrowDown' ? 1 : -1
          setActive((index) => (index + step + options.length) % options.length)
        }
        if (event.key === 'Enter' && open) {
          event.preventDefault()
          choose(options[active])
        }
      }}
    >
      <button
        type="button"
        className="glass select-btn"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`${label}: ${current?.label ?? ''}`}
        onClick={() => (open ? setOpen(false) : show())}
      >
        <span className="select-value">{current?.label}</span>
        <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {open && (
        <div className="menu select-menu" role="listbox" aria-label={label}>
          {options.map((option, index) => (
            <button
              key={option.value}
              type="button"
              role="option"
              aria-selected={option.value === value}
              className={index === active ? 'active' : undefined}
              onMouseEnter={() => setActive(index)}
              onClick={() => choose(option)}
            >
              <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{option.label}</span>
              {option.hint && <span className="tiny muted num">{option.hint}</span>}
              {option.value === value && (
                <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M5 12l5 5 9-10" />
                </svg>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// Ссылка «назад» в шапке страницы, в стиле кнопок
export function BackLink({ href, children }: { href: string; children: string }) {
  return (
    <a href={href} className="btn secondary small back-link">
      <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
        <path d="M15 6l-6 6 6 6" />
      </svg>
      {children}
    </a>
  )
}
