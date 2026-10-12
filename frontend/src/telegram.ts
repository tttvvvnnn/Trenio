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
export function setupTelegram(): string | null {
  if (!isTMA()) {
    return null
  }
  init()
  // Цвета темы Telegram становятся CSS-переменными --tg-theme-*
  mountThemeParamsSync.ifAvailable()
  bindThemeParamsCssVars.ifAvailable()
  mountMiniAppSync.ifAvailable()
  miniAppReady.ifAvailable()
  return retrieveRawInitData() ?? null
}
