import {
  addToHomeScreen,
  backButton,
  checkHomeScreenStatus,
  bindThemeParamsCssVars,
  closeMiniApp,
  disableVerticalSwipes,
  hapticFeedback,
  init,
  isTMA,
  isThemeParamsDark,
  mainButton,
  miniAppReady,
  mountBackButton,
  mountMainButton,
  mountMiniAppSync,
  mountSwipeBehavior,
  mountThemeParamsSync,
  openTelegramLink,
  popup,
  retrieveRawInitData,
  setMiniAppBackgroundColor,
  setMiniAppBottomBarColor,
  setMiniAppHeaderColor,
  shareURL,
} from '@telegram-apps/sdk'

/**
 * Подключается к Telegram и возвращает подписанную initData.
 * Вне Telegram (обычный браузер) возвращает null.
 */
let initialized = false

// Цвета нижней кнопки Telegram: фирменный коралл вместо цвета кнопки из темы
const ACCENT = '#e5421e'
const ON_ACCENT = '#ffffff'

/*
 * Telegram для Android пишет в User-Agent класс производительности устройства:
 * «Telegram-Android/11.2.3 (Samsung SM-A115F; Android 12; SDK 31; LOW)».
 * На слабых телефонах размытие тормозит прокрутку, поэтому стекло там выключаем.
 */
function isLowEndAndroid(): boolean {
  return /Telegram-Android\/[^(]*\([^)]*;\s*LOW\)/.test(navigator.userAgent)
}

export function setupTelegram(): string | null {
  if (isLowEndAndroid()) {
    document.documentElement.classList.add('no-glass')
  }
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
  // Светлая или тёмная тема Telegram: от неё зависят свои цвета стекла и коралла
  const applyScheme = () => {
    document.documentElement.dataset.scheme = isThemeParamsDark() ? 'dark' : 'light'
  }
  applyScheme()
  isThemeParamsDark.sub(applyScheme)
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

/** Выбор из двух вариантов во всплывающем окне Telegram. null — передумали. */
export async function chooseAction<T extends string>(
  message: string,
  options: [[T, string], [T, string]],
): Promise<T | null> {
  if (popup.open.isAvailable()) {
    const id = await popup.open({
      message,
      buttons: [
        { id: options[0][0], type: 'default', text: options[0][1] },
        { id: options[1][0], type: 'default', text: options[1][1] },
        { type: 'cancel' },
      ],
    })
    return options.some(([value]) => value === id) ? (id as T) : null
  }
  // Вне Telegram (разработка): «ОК» — первый вариант, «Отмена» — второй
  return window.confirm(`${message}\nОК — ${options[0][1]}, Отмена — ${options[1][1]}`)
    ? options[0][0]
    : options[1][0]
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
    backgroundColor: ACCENT,
    textColor: ON_ACCENT,
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

/** Окно «Поделиться» Telegram: выбрать чат и отправить ссылку. */
export function shareLink(url: string, text: string): void {
  if (shareURL.isAvailable()) {
    shareURL(url, text)
    return
  }
  const params = new URLSearchParams({ url, text })
  window.open(`https://t.me/share/url?${params}`, '_blank')
}

/** Открыть ссылку t.me внутри Telegram: чат с человеком или ботом. */
export function openTelegram(url: string): void {
  if (openTelegramLink.isAvailable()) {
    openTelegramLink(url)
    return
  }
  window.open(url, '_blank')
}

/** Закрыть Mini App; вне Telegram ничего не делает. */
export function closeApp(): void {
  if (closeMiniApp.isAvailable()) closeMiniApp()
}

/*
 * Значок Trenio на экране телефона. Telegram умеет это с версии 8.0 и не везде:
 * на десктопе и в старых версиях функции нет, тогда строку и плашку не показываем.
 */
export const homeScreen = {
  supported(): boolean {
    return addToHomeScreen.isAvailable()
  },
  // true — значок уже есть, false — нет или Telegram не знает
  async added(): Promise<boolean> {
    if (!checkHomeScreenStatus.isAvailable()) return false
    try {
      return (await checkHomeScreenStatus()) === 'added'
    } catch {
      return false
    }
  },
  add() {
    addToHomeScreen.ifAvailable()
  },
}
