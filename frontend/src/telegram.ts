import {
  backButton,
  bindThemeParamsCssVars,
  disableVerticalSwipes,
  hapticFeedback,
  init,
  isTMA,
  mainButton,
  miniAppReady,
  mountBackButton,
  mountMainButton,
  mountMiniAppSync,
  mountSwipeBehavior,
  mountThemeParamsSync,
  popup,
  retrieveRawInitData,
  setMiniAppBackgroundColor,
  setMiniAppBottomBarColor,
  setMiniAppHeaderColor,
} from '@telegram-apps/sdk'

/**
 * Подключается к Telegram и возвращает подписанную initData.
 * Вне Telegram (обычный браузер) возвращает null.
 */
let initialized = false

export function setupTelegram(): string | null {
  if (!isTMA()) {
    return null
  }
  // StrictMode в разработке запускает эффекты дважды, а повторная привязка CSS-переменных падает
  if (initialized) {
    return retrieveRawInitData() ?? null
  }
  initialized = true
  init()
  // Цвета темы Telegram становятся CSS-переменными --tg-theme-*
  mountThemeParamsSync.ifAvailable()
  bindThemeParamsCssVars.ifAvailable()
  mountMiniAppSync.ifAvailable()
  // Шапка и фон Telegram в цвет фона приложения, чтобы не было полосы на стыке
  setMiniAppHeaderColor.ifAvailable('secondary_bg_color')
  setMiniAppBackgroundColor.ifAvailable('secondary_bg_color')
  setMiniAppBottomBarColor.ifAvailable('bg_color')
  mountMainButton.ifAvailable()
  mountBackButton.ifAvailable()
  // Без этого свайп вниз по длинному списку сворачивает приложение
  mountSwipeBehavior.ifAvailable()
  disableVerticalSwipes.ifAvailable()
  miniAppReady.ifAvailable()
  return retrieveRawInitData() ?? null
}

export const haptic = {
  // Выбор вкладки, дня, чипа
  select() {
    hapticFeedback.selectionChanged.ifAvailable()
  },
  // Нажатие переключателя или степпера
  tap() {
    hapticFeedback.impactOccurred.ifAvailable('light')
  },
  success() {
    hapticFeedback.notificationOccurred.ifAvailable('success')
  },
  error() {
    hapticFeedback.notificationOccurred.ifAvailable('error')
  },
}

/** Подтверждение опасного действия: попап Telegram, вне Telegram обычный confirm. */
export async function confirmAction(message: string, actionText: string): Promise<boolean> {
  if (popup.open.isAvailable()) {
    const id = await popup.open({
      message,
      buttons: [{ id: 'ok', type: 'destructive', text: actionText }, { type: 'cancel' }],
    })
    return id === 'ok'
  }
  return window.confirm(message)
}

export function hasNativeMainButton(): boolean {
  return mainButton.setParams.isAvailable()
}

export function hasNativeBackButton(): boolean {
  return backButton.show.isAvailable()
}

type MainButtonParams = {
  text: string
  visible: boolean
  enabled: boolean
  loading: boolean
}

export function showMainButton({ text, visible, enabled, loading }: MainButtonParams): void {
  mainButton.setParams.ifAvailable({
    text,
    isVisible: visible,
    isEnabled: enabled,
    isLoaderVisible: loading,
  })
}

export function onMainButtonClick(handler: () => void): () => void {
  const [called, off] = mainButton.onClick.ifAvailable(handler)
  return called ? off : () => {}
}

export function setBackButton(visible: boolean): void {
  if (visible) {
    backButton.show.ifAvailable()
  } else {
    backButton.hide.ifAvailable()
  }
}

export function onBackButtonClick(handler: () => void): () => void {
  const [called, off] = backButton.onClick.ifAvailable(handler)
  return called ? off : () => {}
}
