export type Theme = 'light' | 'dark'

const KEY = 'trenio-admin-theme'

// Выбор хранится в браузере; по умолчанию — как в системе
export function savedTheme(): Theme {
  try {
    const value = localStorage.getItem(KEY)
    if (value === 'light' || value === 'dark') return value
  } catch {
    // хранилище недоступно: просто не помним выбор
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme
  try {
    localStorage.setItem(KEY, theme)
  } catch {
    // см. выше
  }
}
