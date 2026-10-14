import type { Booking } from '../api'
import { dayTitle, fullName, localDate, localTime } from '../format'
import { haptic } from '../telegram'
import { PersonAvatar, TrainerAvatar } from './Avatar'

// «идёт сейчас», «через 40 мин», «сегодня», «завтра» или «чт, 16 октября»
function when(booking: Booking, now: Date, timezone: string): string {
  const minutes = Math.round((new Date(booking.starts_at).getTime() - now.getTime()) / 60000)
  if (minutes <= 0) return 'идёт сейчас'
  if (minutes < 60) return `через ${minutes} мин`
  const day = localDate(booking.starts_at, timezone)
  const today = localDate(now, timezone)
  const tomorrow = localDate(new Date(now.getTime() + 24 * 3600 * 1000), timezone)
  if (day === today) return 'сегодня'
  if (day === tomorrow) return 'завтра'
  return dayTitle(day)
}

type Props = {
  booking: Booking
  viewer: 'trainer' | 'client'
  timezone: string
  now: Date
  // Групповое занятие: все записи на это же время и услугу, включая booking
  together?: Booking[]
  onOpen: () => void
}

// Сколько фото показываем стопкой на групповом занятии
const STACK = 3

/** Фирменная карточка ближайшего занятия наверху главного экрана. */
export default function NextSession({
  booking,
  viewer,
  timezone,
  now,
  together = [booking],
  onOpen,
}: Props) {
  // Тренеру важно, кто придёт; клиент и так знает своего тренера, ему важна услуга
  const trainer = viewer === 'trainer'
  const others = together.length - 1
  const title = trainer
    ? fullName(booking.client) + (others > 0 ? ` и ещё ${others}` : '')
    : booking.service.name
  const block = booking.charge ?? booking.planned
  const pills = [trainer ? booking.service.name : booking.trainer.display_name]
  if (booking.status === 'pending') pills.push('ждёт подтверждения')
  if (block) pills.push(`занятие ${block.number} из ${block.sessions_count}`)
  else if (trainer && booking.one_off) pills.push('разовое')
  return (
    <button
      type="button"
      className="next-session"
      onClick={() => {
        haptic.select()
        onOpen()
      }}
    >
      <span className="next-session-text">
        <span className="next-session-kicker">
          Следующее занятие · {when(booking, now, timezone)}
        </span>
        <span className="next-session-title">
          {localTime(booking.starts_at, timezone)} · {title}
        </span>
        <span className="next-session-pills">
          {pills.map((pill) => (
            <span key={pill}>{pill}</span>
          ))}
        </span>
      </span>
      <span className="next-session-avatars">
        {trainer ? (
          together
            .slice(0, STACK)
            .map((item) => <PersonAvatar key={item.id} person={item.client} size="md" />)
        ) : (
          <TrainerAvatar trainer={booking.trainer} size="md" />
        )}
      </span>
    </button>
  )
}
