import { useEffect, useState } from 'react'

import type { Trainer } from '../api'
import { haptic, homeScreen } from '../telegram'
import Icon from '../ui/icons'

const DISMISSED = 'trenio.home-screen-tip'
const DAY_MS = 24 * 60 * 60 * 1000

function dismissed(): boolean {
  try {
    return localStorage.getItem(DISMISSED) !== null
  } catch {
    return false
  }
}

function dismiss() {
  try {
    localStorage.setItem(DISMISSED, '1')
  } catch {
    // Без хранилища плашка вернётся при следующем входе, не страшно
  }
}

/**
 * Один раз, на третий день работы: «Добавьте Trenio на экран телефона».
 * Только там, где Telegram это умеет, и если значка ещё нет. Строка в Профиле остаётся всегда.
 */
export default function HomeScreenTip({ trainer }: { trainer: Trainer }) {
  const [shown, setShown] = useState(false)

  useEffect(() => {
    if (!trainer.onboarded_at || !homeScreen.supported() || dismissed()) return
    if (Date.now() - new Date(trainer.onboarded_at).getTime() < 2 * DAY_MS) return
    let alive = true
    void homeScreen.added().then((added) => {
      if (alive && !added) setShown(true)
    })
    return () => {
      alive = false
    }
  }, [trainer.onboarded_at])

  if (!shown) return null

  function close() {
    dismiss()
    setShown(false)
  }

  return (
    <div className="home-tip">
      <Icon name="smartphone" />
      <span>
        Trenio на экране телефона
        <small>Открывайте записи в одно касание, без поиска бота</small>
      </span>
      <button
        type="button"
        className="home-tip-add"
        onClick={() => {
          haptic.tap()
          homeScreen.add()
          close()
        }}
      >
        Добавить
      </button>
      <button type="button" className="home-tip-close" aria-label="Скрыть" onClick={close}>
        <Icon name="x" />
      </button>
    </div>
  )
}
