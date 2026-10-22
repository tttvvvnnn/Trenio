import { Component, type ReactNode } from 'react'

type State = { error: Error | null }

// Ошибка в одном экране не роняет всю админку: шапка остаётся, а вместо экрана — текст ошибки.
// Сбрасывается сменой key, то есть переходом на другой адрес
export default class ScreenBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <section className="glass tile span-12" role="alert">
        <h2>Экран не открылся</h2>
        <p className="muted" style={{ margin: 0 }}>
          {this.state.error.message}
        </p>
        <div>
          <button type="button" className="btn secondary" onClick={() => this.setState({ error: null })}>
            Повторить
          </button>
        </div>
      </section>
    )
  }
}
