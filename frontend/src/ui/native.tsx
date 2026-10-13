import { useEffect, useRef, useState } from 'react'

import {
  hasNativeBackButton,
  hasNativeMainButton,
  onBackButtonClick,
  onMainButtonClick,
  setBackButton,
  showMainButton,
} from '../telegram'
import Icon from './icons'

/*
 * Кнопки Telegram одни на всё приложение, а экраны вложены друг в друга
 * (список → форма). Поэтому каждый экран кладёт себя в стек,
 * и кнопкой управляет только верхний.
 */

type MainEntry = {
  params: { text: string; visible: boolean; enabled: boolean; loading: boolean }
  onClick: () => void
}

const mainStack: MainEntry[] = []
let offMain: (() => void) | null = null

function syncMain() {
  const top = mainStack[mainStack.length - 1]
  if (top) {
    showMainButton(top.params)
    offMain ??= onMainButtonClick(() => {
      const current = mainStack[mainStack.length - 1]
      if (current?.params.enabled) current.onClick()
    })
  } else {
    showMainButton({ text: 'Сохранить', visible: false, enabled: false, loading: false })
    offMain?.()
    offMain = null
  }
}

type MainButtonProps = {
  text: string
  onClick: () => void
  disabled?: boolean
  loading?: boolean
  visible?: boolean
}

/** Нижняя кнопка Telegram; вне Telegram рисуется обычная кнопка внизу экрана. */
export function MainButton({
  text,
  onClick,
  disabled = false,
  loading = false,
  visible = true,
}: MainButtonProps) {
  const [native] = useState(hasNativeMainButton)
  const entry = useRef<MainEntry | null>(null)

  useEffect(() => {
    if (!native) return
    const current: MainEntry = {
      params: { text: '', visible: false, enabled: false, loading: false },
      onClick: () => {},
    }
    entry.current = current
    mainStack.push(current)
    return () => {
      mainStack.splice(mainStack.indexOf(current), 1)
      syncMain()
    }
    // Параметры выставляет следующий эффект
  }, [native])

  useEffect(() => {
    const current = entry.current
    if (!current) return
    current.params = { text, visible, enabled: !disabled && !loading, loading }
    current.onClick = onClick
    if (mainStack[mainStack.length - 1] === current) syncMain()
  })

  if (native || !visible) return null
  return (
    <div className="main-button-fallback">
      <button type="button" className="button" disabled={disabled || loading} onClick={onClick}>
        {loading ? 'Сохраняем…' : text}
      </button>
    </div>
  )
}

const backStack: { onClick: () => void }[] = []
let offBack: (() => void) | null = null

function syncBack() {
  if (backStack.length > 0) {
    setBackButton(true)
    offBack ??= onBackButtonClick(() => backStack[backStack.length - 1]?.onClick())
  } else {
    setBackButton(false)
    offBack?.()
    offBack = null
  }
}

/** Кнопка «Назад» в шапке Telegram; вне Telegram — ссылка над заголовком. */
export function BackButton({ onClick }: { onClick: () => void }) {
  const [native] = useState(hasNativeBackButton)
  const entry = useRef({ onClick })

  useEffect(() => {
    entry.current.onClick = onClick
  })

  useEffect(() => {
    if (!native) return
    const current = entry.current
    backStack.push(current)
    syncBack()
    return () => {
      backStack.splice(backStack.indexOf(current), 1)
      syncBack()
    }
  }, [native])

  if (native) return null
  return (
    <button type="button" className="back-link" onClick={onClick}>
      <Icon name="chevronLeft" />
      Назад
    </button>
  )
}
