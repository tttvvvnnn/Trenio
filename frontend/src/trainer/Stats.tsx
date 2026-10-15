import { useEffect, useState } from 'react'

import { errorText, fetchTrainerStats, type TrainerStats } from '../api'
import { fullName, localDate, monthTitle, plural, shiftMonth } from '../format'
import { openTelegram } from '../telegram'
import { PersonAvatar } from '../ui/Avatar'
import { ErrorText, Row, Section, SkeletonList } from '../ui/kit'
import Screen from '../ui/Screen'
import { PeriodSwitch, Stat } from './Finance'
import { useRefreshKey } from '../sync'

const WEEKDAYS = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']

type Props = {
  timezone: string
  month: string
  onBack: () => void
}

// 150 -> "2,5 ч"
function hours(minutes: number): string {
  const value = Math.round((minutes / 60) * 10) / 10
  return `${String(value).replace('.', ',')} ч`
}

/** Статистика за месяц: сколько проведено, когда загружен, кто ходит и кто пропал. */
export default function Stats({ timezone, month: initial, onBack }: Props) {
  const [month, setMonth] = useState(initial)
  const [data, setData] = useState<TrainerStats | null>(null)
  const [error, setError] = useState<string | null>(null)
  const refreshKey = useRefreshKey()

  useEffect(() => {
    fetchTrainerStats(month)
      .then(setData)
      .catch((err: unknown) => setError(errorText(err)))
  }, [month, refreshKey])

  const ready = data?.month === month ? data : null

  return (
    <Screen title="Статистика" subtitle="Посещаемость и клиенты" onBack={onBack}>
      <PeriodSwitch
        title={monthTitle(`${month}-01`)}
        onPrev={() => setMonth(shiftMonth(month, -1))}
        onNext={() => setMonth(shiftMonth(month, 1))}
      />
      {error && <ErrorText>{error}</ErrorText>}
      {ready === null && !error && <SkeletonList rows={4} />}
      {ready && <StatsView data={ready} timezone={timezone} />}
    </Screen>
  )
}

function StatsView({ data, timezone }: { data: TrainerStats; timezone: string }) {
  const { visits } = data
  const missed = visits.missed_charged + visits.missed_free
  const marked = visits.attended + missed
  const load = data.load.filter((day) => day.open_minutes > 0 || day.booked_minutes > 0)
  return (
    <>
      <div className="stat-grid">
        <Stat
          label="Проведено"
          value={plural(visits.attended, 'занятие', 'занятия', 'занятий')}
          note={
            marked > 0
              ? `посещаемость ${Math.round((visits.attended / marked) * 100)}%`
              : 'отметок пока нет'
          }
        />
        <Stat
          label="Пропуски"
          value={String(missed)}
          note={missed > 0 ? `со списанием ${visits.missed_charged}` : 'без пропусков'}
          tone={missed > 0 ? 'warning' : undefined}
        />
        <Stat
          label="Отмены"
          value={String(visits.cancelled_by_client + visits.cancelled_by_trainer)}
          note={`клиентами ${visits.cancelled_by_client}, вами ${visits.cancelled_by_trainer}`}
        />
        <Stat label="Новые клиенты" value={String(data.new_clients)} />
      </div>
      {(visits.unmarked > 0 || visits.upcoming > 0) && (
        <p className="section-footer">
          {[
            visits.unmarked > 0 &&
              `Не отмечено: ${plural(visits.unmarked, 'занятие', 'занятия', 'занятий')}.`,
            visits.upcoming > 0 &&
              `Впереди в этом месяце: ${plural(visits.upcoming, 'запись', 'записи', 'записей')}.`,
          ]
            .filter(Boolean)
            .join(' ')}
        </p>
      )}
      {load.length > 0 && (
        <Section
          title="Загрузка по дням недели"
          footer="Сколько рабочего времени из расписания заняли записи за месяц."
        >
          {load.map((day) => {
            const percent =
              day.open_minutes > 0
                ? Math.min(100, Math.round((day.booked_minutes / day.open_minutes) * 100))
                : null
            return (
              <Row
                key={day.weekday}
                title={
                  <span className="funnel-step">
                    <span>{WEEKDAYS[day.weekday]}</span>
                    <b>
                      {percent === null
                        ? `${hours(day.booked_minutes)} вне расписания`
                        : `${percent}% · ${hours(day.booked_minutes)} из ${hours(day.open_minutes)}`}
                    </b>
                    <span className="funnel-bar">
                      <i style={{ width: `${percent ?? 100}%` }} />
                    </span>
                  </span>
                }
              />
            )
          })}
        </Section>
      )}
      {data.top.length > 0 && (
        <Section title="Чаще всех ходили">
          {data.top.map((item) => (
            <Row
              key={item.client.id}
              leading={<PersonAvatar person={item.client} />}
              title={fullName(item.client)}
              value={plural(item.sessions, 'занятие', 'занятия', 'занятий')}
            />
          ))}
        </Section>
      )}
      <Section
        title="Давно не были"
        footer="Не приходили три недели и не записаны на будущее. Напишите им, пока не забыли о вас."
      >
        {data.lapsed.length === 0 && <Row title="Таких нет, все при деле" tone="muted" />}
        {data.lapsed.map((item) => (
          <Row
            key={item.client.id}
            leading={<PersonAvatar person={item.client} />}
            title={fullName(item.client)}
            subtitle={`последний раз ${dayMonth(localDate(item.last_at, timezone))}`}
            after={
              item.client.username ? (
                <button
                  type="button"
                  className="row-action"
                  onClick={() => openTelegram(`https://t.me/${item.client.username}`)}
                >
                  Написать
                </button>
              ) : undefined
            }
          />
        ))}
      </Section>
    </>
  )
}

// "2026-09-01" -> "1 сентября"
function dayMonth(day: string): string {
  return new Intl.DateTimeFormat('ru-RU', {
    timeZone: 'UTC',
    day: 'numeric',
    month: 'long',
  }).format(new Date(`${day}T12:00:00Z`))
}
