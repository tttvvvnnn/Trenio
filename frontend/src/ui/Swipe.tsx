import { useRef, useState, type ReactNode, type TouchEvent } from 'react'

import { haptic } from '../telegram'

export type SwipeAction = {
  label: string
  tone: 'success' | 'muted' | 'planned' | 'destructive'
  onClick: () => void
}

type Props = {
  // Слева направо; крайняя правая — главная
  actions: SwipeAction[]
  // Свайп до конца сразу выполняет это действие
  onFullSwipe?: () => void
  children: ReactNode
}

const ACTION_WIDTH = 100
// Палец ушёл влево дальше открытых кнопок на столько: это свайп до конца
const FULL_EXTRA = 90

// Открытой может быть только одна строка: открыли другую — эта закрывается
let opened: { close: () => void } | null = null

/** Строка со свайпом влево: под ней кнопки быстрых действий. Нажатие работает как обычно. */
export default function SwipeRow({ actions, onFullSwipe, children }: Props) {
  const [offset, setOffsetState] = useState(0)
  // Последнее значение сдвига: события пальца приходят чаще, чем React успевает отрисовать
  const current = useRef(0)
  function setOffset(value: number) {
    current.current = value
    setOffsetState(value)
  }
  const [dragging, setDragging] = useState(false)
  const start = useRef<{ x: number; y: number; from: number } | null>(null)
  // null — направление ещё не понятно, false — человек прокручивает список
  const horizontal = useRef<boolean | null>(null)
  const moved = useRef(false)
  const openWidth = actions.length * ACTION_WIDTH
  const full = onFullSwipe !== undefined && -offset > openWidth + FULL_EXTRA

  // Один объект на всю жизнь строки: по нему понятно, открыта ли именно она
  const [self] = useState(() => ({
    close: () => {
      current.current = 0
      setOffsetState(0)
    },
  }))

  function close() {
    setOffset(0)
    if (opened === self) opened = null
  }

  function onTouchStart(event: TouchEvent) {
    const touch = event.touches[0]
    start.current = { x: touch.clientX, y: touch.clientY, from: current.current }
    horizontal.current = null
    moved.current = false
  }

  function onTouchMove(event: TouchEvent) {
    if (!start.current) return
    const touch = event.touches[0]
    const dx = touch.clientX - start.current.x
    const dy = touch.clientY - start.current.y
    if (horizontal.current === null) {
      if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return
      horizontal.current = Math.abs(dx) > Math.abs(dy)
      if (horizontal.current && opened && opened !== self) {
        opened.close()
        opened = null
      }
    }
    if (!horizontal.current) return
    moved.current = true
    setDragging(true)
    const next = Math.min(0, start.current.from + dx)
    const wasFull = onFullSwipe !== undefined && -current.current > openWidth + FULL_EXTRA
    const isFull = onFullSwipe !== undefined && -next > openWidth + FULL_EXTRA
    if (wasFull !== isFull) haptic.tap()
    setOffset(next)
  }

  function onTouchEnd() {
    if (!start.current) return
    start.current = null
    setDragging(false)
    if (!moved.current) return
    const last = current.current
    if (onFullSwipe !== undefined && -last > openWidth + FULL_EXTRA) {
      setOffset(0)
      onFullSwipe?.()
      return
    }
    if (-last > openWidth / 2) {
      setOffset(-openWidth)
      opened = self
    } else close()
  }

  return (
    <div className="swipe">
      {offset < 0 && (
        <div className="swipe-actions" style={{ width: -offset }}>
          {actions.map((action, index) => (
            <button
              key={action.label}
              type="button"
              className={`swipe-action ${action.tone}`}
              style={full && index === actions.length - 1 ? { flexBasis: '100%' } : undefined}
              onClick={() => {
                close()
                action.onClick()
              }}
            >
              {action.label}
            </button>
          ))}
        </div>
      )}
      <div
        className={dragging ? 'swipe-content dragging' : 'swipe-content'}
        style={offset ? { transform: `translateX(${offset}px)` } : undefined}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        onTouchCancel={onTouchEnd}
        onClickCapture={(event) => {
          // Нажатие по открытой строке закрывает кнопки, а не открывает запись
          if (offset !== 0 || moved.current) {
            event.stopPropagation()
            event.preventDefault()
            moved.current = false
            close()
          }
        }}
      >
        {children}
      </div>
    </div>
  )
}
