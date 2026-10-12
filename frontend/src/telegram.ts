import {
  bindThemeParamsCssVars,
  init,
  isTMA,
  miniAppReady,
  mountMiniAppSync,
  mountThemeParamsSync,
  retrieveRawInitData,
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
  miniAppReady.ifAvailable()
  return retrieveRawInitData() ?? null
}
