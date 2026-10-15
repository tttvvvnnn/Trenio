import { useLayoutEffect, useState, type CSSProperties } from 'react'
import { createPortal } from 'react-dom'

import { haptic } from '../telegram'
import { TOUR_REPLAY } from '../tour'
import { Row, Section } from './kit'

export type TourStep<T extends string> = {
  // Вкладка, которую тур открывает перед шагом
  tab?: T
  // data-tour элемента, который подсвечиваем; без него карточка по центру
  target?: string
  title: string
  text: string
}

type Props<T extends string> = {
  steps: readonly TourStep<T>[]
  onTab: (tab: T) => void
  // И «Пропустить», и «Понятно» на последнем шаге
  onFinish: () => void
}

// Отступ подсветки от элемента и зазор до карточки
const PAD = 6
const GAP = 12
// Сколько ждём, пока экран загрузит данные и элемент появится
const WAIT_MS = 1500

type Rect = { top: number; left: number; width: number; height: number }

/**
 * Вводный тур: затемняет экран, подсвечивает кнопку и объясняет её в карточке.
 * Сам переключает вкладки, чтобы за подсветкой был виден нужный экран.
 */
export default function Tour<T extends string>({ steps, onTab, onFinish }: Props<T>) {
  const [index, setIndex] = useState(0)
  const [rect, setRect] = useState<Rect | null>(null)
  // Пока ищем элемент, карточку не показываем, чтобы она не прыгала
  const [ready, setReady] = useState(false)
  const step = steps[index]
  const last = index === steps.length - 1

  useLayoutEffect(() => {
    setReady(false)
    setRect(null)
    if (step.tab) onTab(step.tab)
    if (!step.target) {
      setReady(true)
      return
    }
    const selector = `[data-tour="${step.target}"]`
    const started = Date.now()
    let element: Element | null = null
    let scrolled = false

    function measure() {
      element ??= document.querySelector(selector)
      if (!element) {
        if (Date.now() - started > WAIT_MS) setReady(true)
        return
      }
      const box = element.getBoundingClientRect()
      // Строка ниже середины экрана или под панелью вкладок: прокручиваем к ней один раз
      if (!scrolled && (box.top < 0 || box.bottom > window.innerHeight - 160)) {
        scrolled = true
        element.scrollIntoView({ block: 'center' })
        return
      }
      setRect((current) => {
        const fresh = {
          top: box.top - PAD,
          left: box.left - PAD,
          width: box.width + PAD * 2,
          height: box.height + PAD * 2,
        }
        return current && sameRect(current, fresh) ? current : fresh
      })
      setReady(true)
    }

    measure()
    // Экран мог догрузить данные и сдвинуть элемент, поэтому меряем регулярно
    const timer = window.setInterval(measure, 120)
    window.addEventListener('resize', measure)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener('resize', measure)
    }
    // onTab меняется на каждый рендер родителя, шаг от него не зависит
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step])

  function go(to: number) {
    haptic.select()
    setIndex(to)
  }

  function finish() {
    haptic.success()
    onFinish()
  }

  return createPortal(
    <div className="tour" role="dialog" aria-modal="true" aria-labelledby="tour-title">
      {rect ? <div className="tour-spot" style={rect} /> : <div className="tour-dim" />}
      {ready && (
        <div
          className={rect ? 'tour-card' : 'tour-card tour-card-centered'}
          style={cardPosition(rect)}
          key={index}
        >
          <div className="tour-head">
            <span className="tour-dots" aria-label={`Шаг ${index + 1} из ${steps.length}`}>
              {steps.map((_, i) => (
                <i key={i} className={i === index ? 'active' : undefined} />
              ))}
            </span>
            {!last && (
              <button type="button" className="tour-skip" onClick={finish}>
                Пропустить
              </button>
            )}
          </div>
          <h2 id="tour-title">{step.title}</h2>
          <p>{step.text}</p>
          <div className="tour-actions">
            {index > 0 && (
              <button type="button" className="tour-back" onClick={() => go(index - 1)}>
                Назад
              </button>
            )}
            <button
              type="button"
              className="button"
              onClick={last ? finish : () => go(index + 1)}
            >
              {last ? 'Понятно' : 'Далее'}
            </button>
          </div>
        </div>
      )}
    </div>,
    document.body,
  )
}

function sameRect(a: Rect, b: Rect) {
  return (
    Math.abs(a.top - b.top) < 1 &&
    Math.abs(a.left - b.left) < 1 &&
    Math.abs(a.width - b.width) < 1 &&
    Math.abs(a.height - b.height) < 1
  )
}

// Карточка над элементом, если он в нижней половине экрана, иначе под ним
function cardPosition(rect: Rect | null): CSSProperties | undefined {
  if (!rect) return undefined
  const below = rect.top + rect.height / 2 < window.innerHeight / 2
  return below
    ? { top: rect.top + rect.height + GAP }
    : { bottom: window.innerHeight - rect.top + GAP }
}

/** Строка в Профиле, которая запускает тур заново. */
export function TourRow({ onClick }: { onClick: () => void }) {
  return (
    <Section footer="Короткий тур по главным экранам.">
      <Row
        title="Как пользоваться"
        icon={{ name: 'help', color: 'var(--c-success)' }}
        chevron
        tourId={TOUR_REPLAY}
        onClick={onClick}
      />
    </Section>
  )
}
