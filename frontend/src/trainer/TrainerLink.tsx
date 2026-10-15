import { useEffect, useState } from 'react'

import { errorText, fetchClients, fetchTrainerBooking, type Booking, type Client } from '../api'
import type { LinkTarget } from '../deeplink'
import LinkNotice from '../ui/LinkNotice'
import BookingDetails from './BookingDetails'
import ClientCard from './ClientCard'

type Props = {
  link: LinkTarget
  timezone: string
}

type Opened = { booking: Booking } | { client: Client } | { notice: string; hint?: string } | null

/** Куда ведёт кнопка из уведомления: заявка, запись или карточка клиента. */
export default function TrainerLink({ link, timezone }: Props) {
  const [opened, setOpened] = useState<Opened>(null)

  useEffect(() => {
    if (link.booking !== undefined) {
      fetchTrainerBooking(link.booking)
        .then((booking) => {
          if (booking.status === 'cancelled') {
            setOpened({
              notice:
                booking.cancelled_by === 'trainer'
                  ? 'Эта запись уже отменена'
                  : 'Эта запись уже отменена клиентом',
            })
          } else if (booking.status === 'declined') {
            setOpened({ notice: 'Эта заявка уже отклонена' })
          } else {
            setOpened({ booking })
          }
        })
        .catch((err: unknown) =>
          setOpened({ notice: 'Не получилось открыть запись', hint: errorText(err) }),
        )
    } else if (link.client !== undefined) {
      const id = link.client
      fetchClients()
        .then((clients) => {
          const client = clients.find((item) => item.id === id)
          setOpened(client ? { client } : { notice: 'Клиент не найден' })
        })
        .catch((err: unknown) =>
          setOpened({ notice: 'Не получилось открыть клиента', hint: errorText(err) }),
        )
    }
  }, [link])

  if (opened === null) return null
  const close = () => setOpened(null)
  if ('notice' in opened)
    return <LinkNotice text={opened.notice} hint={opened.hint} onClose={close} />
  if ('booking' in opened) {
    return (
      <BookingDetails
        booking={opened.booking}
        onBack={close}
        onChanged={(booking) => setOpened({ booking })}
      />
    )
  }
  return (
    <ClientCard client={opened.client} timezone={timezone} onBack={close} onChanged={() => {}} />
  )
}
