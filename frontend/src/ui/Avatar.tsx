import { useState } from 'react'

import { mediaUrl, type Person } from '../api'
import { fullName } from '../format'

// xs — внутри плашек и чипов, sm — в строках списков, md — в карточке, lg — в профиле
export type AvatarSize = 'xs' | 'sm' | 'md' | 'lg'

type Props = {
  name: string
  url: string | null | undefined
  // По нему выбирается цвет круга с инициалами: у одного человека он всегда одинаковый
  seed: number
  size?: AvatarSize
}

// Сколько оттенков у кругов с инициалами, см. .avatar-tone-* в index.css
const TONES = 6

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0].toUpperCase())
    .join('')
}

/** Фото человека, а если его нет или оно не загрузилось — инициалы на цветном круге. */
export default function Avatar({ name, url, seed, size = 'sm' }: Props) {
  // Адрес, который не загрузился: для него показываем инициалы
  const [broken, setBroken] = useState<string | null>(null)
  const className = `avatar avatar-${size}`
  if (url && broken !== url) {
    return (
      <img
        className={className}
        src={mediaUrl(url)}
        alt=""
        aria-hidden="true"
        loading="lazy"
        decoding="async"
        onError={() => setBroken(url)}
      />
    )
  }
  return (
    <span className={`${className} avatar-tone-${Math.abs(seed) % TONES}`} aria-hidden="true">
      {initials(name)}
    </span>
  )
}

/** Фото клиента или другого пользователя. */
export function PersonAvatar({ person, size }: { person: Person; size?: AvatarSize }) {
  return <Avatar name={fullName(person)} url={person.avatar_url} seed={person.id} size={size} />
}

type TrainerRef = { id: number; display_name: string; avatar_url: string | null }

/** Фото тренера: цвет инициалов по id тренера, как в его профиле. */
export function TrainerAvatar({ trainer, size }: { trainer: TrainerRef; size?: AvatarSize }) {
  return (
    <Avatar name={trainer.display_name} url={trainer.avatar_url} seed={trainer.id} size={size} />
  )
}
