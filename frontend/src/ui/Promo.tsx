import { useEffect, useState } from 'react'

import { sendPromoEvent, type Promo, type PromoEvent } from '../api'
import { haptic, openUrl } from '../telegram'
import Icon from './icons'
import { Row, Section } from './kit'
import { MainButton } from './native'
import Screen from './Screen'

const IMAGE = `${import.meta.env.BASE_URL}promo/tvpn.jpg`

// «Показали» отправляем один раз с устройства: в админке считаем людей, а не входы
const SHOWN = 'trenio.promo-shown'

function track(event: PromoEvent) {
  // Счётчик необязательный: если не дошло, ничего не показываем
  sendPromoEvent(event).catch(() => {})
}

function markShown() {
  try {
    if (localStorage.getItem(SHOWN) !== null) return
    localStorage.setItem(SHOWN, '1')
  } catch {
    // Без хранилища отметка уйдёт при каждом показе, сервер учтёт только первую
  }
  track('shown')
}

/**
 * Карточка на главном экране. Сервер решает, пора ли её показать: не раньше чем через
 * несколько дней после первого входа и только пока человек её не закрыл и не открыл код.
 */
export function PromoCard({ promo }: { promo: Promo | null }) {
  const [hidden, setHidden] = useState(false)
  const [opened, setOpened] = useState(false)
  const visible = promo !== null && promo.card && !hidden

  useEffect(() => {
    if (visible) markShown()
  }, [visible])

  if (promo === null || (!visible && !opened)) return null

  return (
    <>
      {visible && (
        <div className="promo-card">
          <img src={IMAGE} alt="" />
          <div className="promo-card-text">
            <span className="promo-card-kicker">Подарок от автора Trenio</span>
            <span className="promo-card-title">{promo.title}</span>
            {promo.subtitle && <span className="promo-card-subtitle">{promo.subtitle}</span>}
            <button
              type="button"
              className="promo-card-claim"
              onClick={() => {
                haptic.tap()
                setOpened(true)
                setHidden(true)
              }}
            >
              Забрать
            </button>
          </div>
          <button
            type="button"
            className="promo-card-close"
            aria-label="Скрыть"
            onClick={() => {
              haptic.tap()
              track('dismissed')
              setHidden(true)
            }}
          >
            <Icon name="x" />
          </button>
        </div>
      )}
      {opened && <PromoScreen promo={promo} onBack={() => setOpened(false)} />}
    </>
  )
}

/** Тихая строка внизу Профиля: код можно найти и после того, как карточку закрыли. */
export function PromoSection({ promo }: { promo: Promo | null }) {
  const [opened, setOpened] = useState(false)
  if (promo === null) return null
  return (
    <>
      <Section title="От автора Trenio">
        <Row
          title={promo.title}
          subtitle={`Промокод ${promo.code}`}
          leading={<img className="promo-row-image" src={IMAGE} alt="" />}
          chevron
          onClick={() => setOpened(true)}
        />
      </Section>
      {opened && <PromoScreen promo={promo} onBack={() => setOpened(false)} />}
    </>
  )
}

type ScreenProps = {
  promo: Omit<Promo, 'card'>
  onBack: () => void
  // Предпросмотр из админ-панели: без счётчиков
  preview?: boolean
}

/** Экран с промокодом и кнопкой перехода. */
export function PromoScreen({ promo, onBack, preview = false }: ScreenProps) {
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!preview) track('claimed')
  }, [preview])

  async function copy() {
    try {
      await navigator.clipboard.writeText(promo.code)
      haptic.success()
      setCopied(true)
    } catch {
      // Код и так крупно на экране, его можно переписать
      haptic.error()
    }
  }

  return (
    <Screen
      title={promo.title}
      onBack={onBack}
      header={
        <header className="promo-hero">
          <img src={IMAGE} alt="" />
          <h1>{promo.title}</h1>
          {promo.text && <p>{promo.text}</p>}
        </header>
      }
    >
      <div className="promo-code">
        <div>
          <span className="promo-code-label">Промокод</span>
          <span className="promo-code-value">{promo.code}</span>
        </div>
        <button type="button" onClick={() => void copy()}>
          <Icon name={copied ? 'check' : 'copy'} />
          {copied ? 'Скопировано' : 'Скопировать'}
        </button>
      </div>
      <Section>
        <Row title="Скопируйте код" leading={<span className="promo-step">1</span>} />
        <Row title={`Нажмите «${promo.button}»`} leading={<span className="promo-step">2</span>} />
        <Row title="Введите код при подключении" leading={<span className="promo-step">3</span>} />
      </Section>
      <p className="promo-fine">
        Предложение от автора Trenio. Карточку на главном можно скрыть, код останется в Профиле.
      </p>
      <MainButton
        text={promo.button}
        onClick={() => {
          haptic.tap()
          if (!preview) track('opened')
          openUrl(promo.url)
        }}
      />
    </Screen>
  )
}
