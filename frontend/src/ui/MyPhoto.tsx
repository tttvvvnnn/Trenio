import { useEffect, useRef, useState } from 'react'

import {
  errorText,
  fetchMe,
  removeAvatar,
  restoreTelegramAvatar,
  uploadAvatar,
  type AvatarState,
  type Me,
} from '../api'
import { fullName } from '../format'
import { haptic } from '../telegram'
import Avatar from './Avatar'
import { ErrorText, Row, Section } from './kit'

// Сторона квадрата, до которой сжимаем своё фото: с запасом для крупного круга в профиле
const PHOTO_SIDE = 320

/** Вырезает квадрат из середины картинки и сжимает в JPEG. */
async function squareJpeg(file: File): Promise<Blob> {
  const url = URL.createObjectURL(file)
  try {
    const image = new Image()
    image.src = url
    await image.decode()
    const side = Math.min(image.naturalWidth, image.naturalHeight)
    const canvas = document.createElement('canvas')
    canvas.width = PHOTO_SIDE
    canvas.height = PHOTO_SIDE
    const context = canvas.getContext('2d')
    if (!context || side === 0) throw new Error('Не удалось открыть фото')
    context.drawImage(
      image,
      (image.naturalWidth - side) / 2,
      (image.naturalHeight - side) / 2,
      side,
      side,
      0,
      0,
      PHOTO_SIDE,
      PHOTO_SIDE,
    )
    return await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob(
        (blob) => (blob ? resolve(blob) : reject(new Error('Не удалось сжать фото'))),
        'image/jpeg',
        0.85,
      ),
    )
  } catch {
    throw new Error('Не получилось открыть это фото. Попробуйте другое.')
  } finally {
    URL.revokeObjectURL(url)
  }
}

type Props = {
  // Имя для инициалов, пока фото нет; по умолчанию имя из Telegram
  name?: string
  // Цвет круга с инициалами; по умолчанию по id пользователя
  seed?: number
  // hero — крупно наверху профиля тренера, section — строками в списке
  variant: 'hero' | 'section'
  // Подпись под именем в hero
  caption?: string
}

/** Своё фото: из Telegram, загруженное или никакого. Меняется здесь же. */
export default function MyPhoto({ name, seed, variant, caption }: Props) {
  const [state, setState] = useState<AvatarState | null>(null)
  const [me, setMe] = useState<Me | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    fetchMe()
      .then((loaded) => {
        setMe(loaded)
        setState({ avatar_url: loaded.avatar_url, avatar_mode: loaded.avatar_mode })
      })
      .catch(() => setState(null))
  }, [])

  async function run(action: () => Promise<AvatarState>) {
    setBusy(true)
    setError(null)
    try {
      setState(await action())
      haptic.success()
    } catch (err) {
      haptic.error()
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  // Выбор файла открываем прямо в обработчике нажатия: иначе браузер его не покажет
  function pick() {
    haptic.tap()
    input.current?.click()
  }

  const url = state?.avatar_url ?? null
  const shownName = name ?? (me ? fullName(me) : '')
  const shownSeed = seed ?? me?.id ?? 0
  const fromTelegram = state?.avatar_mode === 'telegram'
  const fileInput = (
    <input
      ref={input}
      type="file"
      accept="image/*"
      hidden
      onChange={(event) => {
        const file = event.target.files?.[0]
        event.target.value = ''
        if (file) void run(async () => uploadAvatar(await squareJpeg(file)))
      }}
    />
  )

  if (variant === 'hero') {
    return (
      <div className="hero">
        <button type="button" className="hero-photo" onClick={pick} disabled={busy}>
          <Avatar name={shownName} url={url} seed={shownSeed} size="lg" />
        </button>
        <strong>{shownName}</strong>
        {caption && <span>{caption}</span>}
        <div className="photo-edit">
          <button type="button" onClick={pick} disabled={busy}>
            {url ? 'Заменить фото' : 'Загрузить фото'}
          </button>
          {state && !fromTelegram && (
            <button type="button" onClick={() => void run(restoreTelegramAvatar)} disabled={busy}>
              Из Telegram
            </button>
          )}
          {url && (
            <button
              type="button"
              className="destructive"
              onClick={() => void run(removeAvatar)}
              disabled={busy}
            >
              Убрать
            </button>
          )}
        </div>
        {error && <ErrorText>{error}</ErrorText>}
        {fileInput}
      </div>
    )
  }

  return (
    <>
      <Section
        title="Ваше фото"
        footer="Его видит тренер в записях. По умолчанию берём фото из Telegram."
      >
        <Row
          leading={<Avatar name={shownName} url={url} seed={shownSeed} size="sm" />}
          title={url ? 'Заменить фото' : 'Загрузить фото'}
          tone="accent"
          onClick={busy ? undefined : pick}
        />
        {state && !fromTelegram && (
          <Row
            title="Взять фото из Telegram"
            tone="accent"
            onClick={busy ? undefined : () => void run(restoreTelegramAvatar)}
          />
        )}
        {url && (
          <Row
            title="Убрать фото"
            tone="destructive"
            onClick={busy ? undefined : () => void run(removeAvatar)}
          />
        )}
        {fileInput}
      </Section>
      {error && <ErrorText>{error}</ErrorText>}
    </>
  )
}
