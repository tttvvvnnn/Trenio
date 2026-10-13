import { useState } from 'react'

import { PageHeader, Segmented } from '../ui/kit'
import Days from './Days'
import WeekTemplate from './WeekTemplate'

type View = 'week' | 'days'

type Props = {
  timezone: string
}

export default function Schedule({ timezone }: Props) {
  const [view, setView] = useState<View>('week')
  return (
    <>
      <PageHeader title="Расписание" />
      <Segmented
        label="Раздел расписания"
        value={view}
        options={[
          ['week', 'Обычная неделя'],
          ['days', 'Исключения'],
        ]}
        onChange={setView}
      />
      {view === 'week' ? <WeekTemplate /> : <Days timezone={timezone} />}
    </>
  )
}
