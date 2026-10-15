import { useEffect, useState } from 'react'

import { fetchMyBookings, type Booking } from '../api'
import { nextBooking } from '../calendar'
import { useRefreshKey } from '../sync'
import { PageHeader, Segmented } from '../ui/kit'
import NextSession from '../ui/NextSession'
import MyBookings from './MyBookings'
import { ActiveBlocks, MyProgress, PastBlocks } from './MyPackages'

type View = 'upcoming' | 'history' | 'progress'

type Props = {
  onBook: () => void
}

/** «Мои занятия»: ближайшее, блоки, записи и прогресс на одной вкладке. */
export default function MySessions({ onBook }: Props) {
  const [view, setView] = useState<View>('upcoming')
  const [next, setNext] = useState<Booking | null>(null)
  const refreshKey = useRefreshKey()

  useEffect(() => {
    // Карточка необязательная: если не загрузилась, просто не показываем
    fetchMyBookings()
      .then((items) => setNext(nextBooking(items, new Date())))
      .catch(() => setNext(null))
  }, [refreshKey])

  return (
    <>
      <PageHeader title="Мои занятия" />
      {next && (
        <NextSession
          booking={next}
          viewer="client"
          timezone={next.trainer.timezone}
          now={new Date()}
          onOpen={() => setView('upcoming')}
        />
      )}
      <ActiveBlocks />
      <Segmented
        label="Что показать"
        value={view}
        options={[
          ['upcoming', 'Предстоящие'],
          ['history', 'История'],
          ['progress', 'Прогресс'],
        ]}
        onChange={setView}
      />
      {view === 'upcoming' && <MyBookings view="upcoming" onBook={onBook} />}
      {view === 'history' && (
        <>
          <MyBookings view="history" onBook={onBook} />
          <PastBlocks />
        </>
      )}
      {view === 'progress' && <MyProgress />}
    </>
  )
}
