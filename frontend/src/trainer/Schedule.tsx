import { useState } from 'react'

import { PageHeader, Segmented } from '../ui/kit'
import ScheduleCalendar from './ScheduleCalendar'
import WeekTemplate from './WeekTemplate'

type View = 'calendar' | 'week'

type Props = {
  timezone: string
}

export default function Schedule({ timezone }: Props) {
  const [view, setView] = useState<View>('calendar')
  return (
    <>
      <PageHeader title="Расписание" />
      <Segmented
        label="Раздел расписания"
        value={view}
        options={[
          ['calendar', 'Календарь'],
          ['week', 'Шаблон недели'],
        ]}
        onChange={setView}
      />
      {view === 'calendar' ? <ScheduleCalendar timezone={timezone} /> : <WeekTemplate />}
    </>
  )
}
