import { useEffect, useState } from 'react'

import { errorText, fetchMyBooking, type Booking } from '../api'
import type { LinkTarget } from '../deeplink'
import LinkNotice from '../ui/LinkNotice'
import { BookingDetails } from './MyBookings'

type Opened = { booking: Booking } | { notice: string; hint?: string } | null

/** Своя запись по кнопке из уведомления. Отменённую не открываем, а говорим об этом. */
export default function ClientLink({ link }: { link: LinkTarget }) {
  const [opened, setOpened] = useState<Opened>(null)

  useEffect(() => {
    if (link.booking === undefined) return
    fetchMyBooking(link.booking)
      .then((booking) => {
        if (booking.status === 'cancelled') {
          setOpened({
            notice: 'Эта запись уже отменена',
            hint: booking.cancelled_by === 'trainer' ? 'Её отменил тренер' : undefined,
          })
        } else if (booking.status === 'declined') {
          setOpened({ notice: 'Тренер не смог принять эту запись', hint: 'Выберите другое время' })
        } else {
          setOpened({ booking })
        }
      })
      .catch((err: unknown) =>
        setOpened({ notice: 'Не получилось открыть запись', hint: errorText(err) }),
      )
  }, [link])

  if (opened === null) return null
  const close = () => setOpened(null)
  if ('notice' in opened)
    return <LinkNotice text={opened.notice} hint={opened.hint} onClose={close} />
  return (
    <BookingDetails
      booking={opened.booking}
      onBack={close}
      onChanged={(booking) => setOpened({ booking })}
    />
  )
}
