import { Component, type ErrorInfo, type ReactNode } from 'react'

import { reportError } from '../errors'
import { BrandWordmark } from './BrandMark'

export function CrashScreen() {
  return (
    <div className="crash" role="alert">
      <BrandWordmark height={34} spinning />
      <h1>Что-то пошло не так</h1>
      <p>Мы уже получили сообщение об ошибке. Обновите экран: ваши записи на месте.</p>
      <button type="button" className="crash-button" onClick={() => window.location.reload()}>
        Обновить
      </button>
    </div>
  )
}

type Props = { children: ReactNode }

/** Если экран упал при отрисовке, вместо белого экрана показываем CrashScreen. */
export class ErrorBoundary extends Component<Props, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Первая строка стека компонентов: «at ClientCard (адрес файла)», нужно только имя
    const where = info.componentStack?.match(/at (\w+)/)?.[1]
    reportError(error, where)
  }

  render() {
    return this.state.failed ? <CrashScreen /> : this.props.children
  }
}
