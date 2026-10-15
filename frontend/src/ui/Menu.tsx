import { useEffect, useRef, useState } from 'react'

import { haptic } from '../telegram'

type Item = { label: string; onClick: () => void }

/** Кнопка «⋯» с коротким списком редких действий. */
export default function Menu({ label, items }: { label: string; items: Item[] }) {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)

  // Нажатие мимо меню его закрывает
  useEffect(() => {
    if (!open) return
    function onDown(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', onDown)
    return () => document.removeEventListener('pointerdown', onDown)
  }, [open])

  return (
    <div className="menu" ref={root}>
      <button
        type="button"
        className="menu-button"
        aria-label={label}
        aria-expanded={open}
        onClick={() => {
          haptic.tap()
          setOpen(!open)
        }}
      >
        ⋯
      </button>
      {open && (
        <div className="menu-list" role="menu">
          {items.map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false)
                item.onClick()
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
