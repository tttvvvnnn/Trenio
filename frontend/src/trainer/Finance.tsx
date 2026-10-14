import { useEffect, useState } from 'react'

import {
  fetchFinanceForecast,
  fetchFinanceMonth,
  fetchFinanceSummary,
  fetchFinanceYear,
  type FinanceForecast,
  type FinanceMonth,
  type FinanceSummary,
  type FinanceYear,
  type MonthPoint,
} from '../api'
import { fullName, localDate, monthTitle, plural, rubles } from '../format'
import { haptic } from '../telegram'
import { PersonAvatar } from '../ui/Avatar'
import Icon from '../ui/icons'
import { ErrorText, PageHeader, Row, Section, Segmented, SkeletonList } from '../ui/kit'
import Screen from '../ui/Screen'

type Props = {
  timezone: string
}

type View = 'month' | 'year'

// "2026-10", -1 -> "2026-09"
function shiftMonth(month: string, by: number): string {
  const [year, number] = month.split('-').map(Number)
  const index = year * 12 + number - 1 + by
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, '0')}`
}

// "2026-10" -> "окт"; три буквы, чтобы 12 месяцев года помещались в ряд
function monthShort(month: string): string {
  return new Intl.DateTimeFormat('ru-RU', { timeZone: 'UTC', month: 'short' })
    .format(new Date(`${month}-15T12:00:00Z`))
    .replace('.', '')
    .slice(0, 3)
}

// "2026-10-12" -> "12 окт"
function dayShort(day: string): string {
  return `${Number(day.slice(8, 10))} ${monthShort(day.slice(0, 7))}`
}

// +12% к прошлому месяцу; без прошлых денег сравнивать не с чем
function change(current: number, previous: number): string | null {
  if (previous <= 0) return null
  const percent = Math.round(((current - previous) / previous) * 100)
  return `${percent > 0 ? '+' : ''}${percent}% к прошлому месяцу`
}

export default function Finance({ timezone }: Props) {
  const today = localDate(new Date(), timezone)
  const thisMonth = today.slice(0, 7)
  const [view, setView] = useState<View>('month')
  const [month, setMonth] = useState(thisMonth)
  const [year, setYear] = useState(Number(today.slice(0, 4)))
  const [summary, setSummary] = useState<FinanceSummary | null>(null)
  const [yearData, setYearData] = useState<FinanceYear | null>(null)
  const [opened, setOpened] = useState<'details' | 'forecast' | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (view !== 'month') return
    fetchFinanceSummary(month)
      .then(setSummary)
      .catch((err: unknown) => setError(String(err)))
  }, [view, month])

  useEffect(() => {
    if (view !== 'year') return
    fetchFinanceYear(year)
      .then(setYearData)
      .catch((err: unknown) => setError(String(err)))
  }, [view, year])

  function openMonth(next: string) {
    haptic.select()
    setMonth(next)
    setView('month')
  }

  const monthReady = summary?.month === month ? summary : null
  const yearReady = yearData?.year === year ? yearData : null

  return (
    <>
      <PageHeader title="Финансы" subtitle="Деньги учитываются по оплатам, которые вы отмечаете." />
      <div className="finance-switch">
        <Segmented
          label="Период"
          value={view}
          options={[
            ['month', 'Месяц'],
            ['year', 'Год'],
          ]}
          onChange={setView}
        />
      </div>
      {error && <ErrorText>{error}</ErrorText>}
      {view === 'month' && (
        <>
          <PeriodSwitch
            title={monthTitle(`${month}-01`)}
            onPrev={() => setMonth(shiftMonth(month, -1))}
            onNext={() => setMonth(shiftMonth(month, 1))}
          />
          {monthReady === null && !error && <SkeletonList rows={3} />}
          {monthReady && (
            <MonthView
              summary={monthReady}
              current={month === thisMonth}
              onMonth={openMonth}
              onDetails={() => setOpened('details')}
              onForecast={() => setOpened('forecast')}
            />
          )}
        </>
      )}
      {view === 'year' && (
        <>
          <PeriodSwitch
            title={String(year)}
            onPrev={() => setYear(year - 1)}
            onNext={() => setYear(year + 1)}
          />
          {yearReady === null && !error && <SkeletonList rows={3} />}
          {yearReady && <YearView data={yearReady} onMonth={openMonth} />}
        </>
      )}
      {opened === 'details' && <MonthDetails month={month} onBack={() => setOpened(null)} />}
      {opened === 'forecast' && <Forecast onBack={() => setOpened(null)} />}
    </>
  )
}

function PeriodSwitch({
  title,
  onPrev,
  onNext,
}: {
  title: string
  onPrev: () => void
  onNext: () => void
}) {
  return (
    <div className="month-head finance-period">
      <button type="button" className="month-arrow" aria-label="Назад" onClick={onPrev}>
        <Icon name="chevronLeft" />
      </button>
      <h2>{title}</h2>
      <button type="button" className="month-arrow" aria-label="Вперёд" onClick={onNext}>
        <Icon name="chevronRight" />
      </button>
    </div>
  )
}

type MonthViewProps = {
  summary: FinanceSummary
  current: boolean
  onMonth: (month: string) => void
  onDetails: () => void
  onForecast: () => void
}

function MonthView({ summary, current, onMonth, onDetails, onForecast }: MonthViewProps) {
  const pills = [
    change(summary.received, summary.received_prev),
    summary.incomes_count > 0
      ? plural(summary.incomes_count, 'поступление', 'поступления', 'поступлений')
      : null,
  ].filter((pill): pill is string => pill !== null)
  return (
    <>
      <div className="money-hero">
        <span className="money-hero-kicker">Получено за месяц</span>
        <span className="money-hero-amount">{rubles(summary.received)}</span>
        {pills.length > 0 && (
          <span className="next-session-pills">
            {pills.map((pill) => (
              <span key={pill}>{pill}</span>
            ))}
          </span>
        )}
      </div>
      <div className="stat-grid">
        <Stat
          label="Отработано"
          value={rubles(summary.worked)}
          note={plural(summary.worked_sessions, 'занятие', 'занятия', 'занятий')}
        />
        {current || summary.planned_count > 0 ? (
          <Stat
            label="До конца месяца"
            value={`≈ ${rubles(summary.planned)}`}
            note={plural(summary.planned_count, 'запись', 'записи', 'записей')}
          />
        ) : (
          <Stat
            label="Занимались"
            value={plural(summary.clients, 'клиент', 'клиента', 'клиентов')}
          />
        )}
        <Stat
          label="Ждём доплат"
          value={rubles(summary.debt)}
          note={
            summary.debt_clients > 0
              ? plural(summary.debt_clients, 'клиент', 'клиента', 'клиентов')
              : 'долгов нет'
          }
          tone={summary.debt > 0 ? 'warning' : undefined}
          onClick={onForecast}
        />
        <Stat label="Аванс клиентов" value={rubles(summary.advance)} note="ещё не отработано" />
      </div>
      <Section title="По месяцам">
        <BarChart points={summary.chart} selected={summary.month} onSelect={onMonth} />
      </Section>
      {summary.received > 0 && (
        <Section title="Откуда деньги">
          <Row title="Блоки" value={rubles(summary.from_packages)} />
          <Row title="Разовые занятия" value={rubles(summary.from_one_off)} />
        </Section>
      )}
      <Section footer="Разовое занятие считается оплаченным по цене услуги, когда вы отмечаете его.">
        <Row
          title="Подробности месяца"
          subtitle="Поступления и клиенты"
          icon={{ name: 'list', color: 'var(--c-violet)' }}
          chevron
          onClick={onDetails}
        />
        <Row
          title="Прогноз на 30 дней"
          subtitle="Доплаты, продления блоков и разовые"
          icon={{ name: 'wallet', color: 'var(--c-accent)' }}
          chevron
          onClick={onForecast}
        />
      </Section>
    </>
  )
}

function YearView({ data, onMonth }: { data: FinanceYear; onMonth: (month: string) => void }) {
  return (
    <>
      <div className="money-hero">
        <span className="money-hero-kicker">Получено за {data.year} год</span>
        <span className="money-hero-amount">{rubles(data.received)}</span>
      </div>
      <div className="stat-grid">
        <Stat label="Отработано" value={rubles(data.worked)} />
        <Stat
          label="Проведено"
          value={plural(data.worked_sessions, 'занятие', 'занятия', 'занятий')}
        />
      </div>
      <Section title="По месяцам" footer="Нажмите на месяц, чтобы открыть его.">
        <BarChart points={data.months} onSelect={onMonth} />
      </Section>
      <Section>
        {data.months
          .filter((point) => point.received > 0 || point.worked > 0)
          .reverse()
          .map((point) => (
            <Row
              key={point.month}
              title={monthTitle(`${point.month}-01`).split(' ')[0]}
              subtitle={`отработано ${rubles(point.worked)}`}
              value={rubles(point.received)}
              chevron
              onClick={() => onMonth(point.month)}
            />
          ))}
      </Section>
    </>
  )
}

type StatProps = {
  label: string
  value: string
  note?: string
  tone?: 'warning'
  onClick?: () => void
}

function Stat({ label, value, note, tone, onClick }: StatProps) {
  const content = (
    <>
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      {note && <span className={tone ? `stat-note ${tone}` : 'stat-note'}>{note}</span>}
    </>
  )
  if (!onClick) return <div className="stat-tile">{content}</div>
  return (
    <button
      type="button"
      className="stat-tile"
      onClick={() => {
        haptic.select()
        onClick()
      }}
    >
      {content}
    </button>
  )
}

type BarChartProps = {
  points: MonthPoint[]
  selected?: string
  onSelect: (month: string) => void
}

/** Столбики по месяцам: заливка — получено, контур — отработано. */
function BarChart({ points, selected, onSelect }: BarChartProps) {
  const max = Math.max(1, ...points.flatMap((p) => [p.received, p.worked]))
  const height = (amount: number) => `${Math.round((amount / max) * 100)}%`
  return (
    <div className="group bar-chart-card">
      <div className="bar-chart" role="list">
        {points.map((point) => (
          <button
            key={point.month}
            type="button"
            role="listitem"
            className="bar-month"
            aria-current={point.month === selected ? 'true' : undefined}
            aria-label={`${monthTitle(`${point.month}-01`)}: получено ${rubles(point.received)}, отработано ${rubles(point.worked)}`}
            onClick={() => onSelect(point.month)}
          >
            <span className="bar-pair">
              <span className="bar received" style={{ height: height(point.received) }} />
              <span className="bar worked" style={{ height: height(point.worked) }} />
            </span>
            <span className="bar-label">{monthShort(point.month)}</span>
          </button>
        ))}
      </div>
      <div className="bar-legend">
        <span>
          <i className="received" />
          получено
        </span>
        <span>
          <i className="worked" />
          отработано
        </span>
        <span className="bar-max">до {rubles(max)}</span>
      </div>
    </div>
  )
}

function MonthDetails({ month, onBack }: { month: string; onBack: () => void }) {
  const [data, setData] = useState<FinanceMonth | null>(null)
  const [tab, setTab] = useState<'incomes' | 'clients'>('incomes')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchFinanceMonth(month)
      .then(setData)
      .catch((err: unknown) => setError(String(err)))
  }, [month])

  return (
    <Screen title={monthTitle(`${month}-01`)} subtitle="Подробности месяца" onBack={onBack}>
      <div className="finance-switch">
        <Segmented
          label="Что показать"
          value={tab}
          options={[
            ['incomes', 'Поступления'],
            ['clients', 'Клиенты'],
          ]}
          onChange={setTab}
        />
      </div>
      {error && <ErrorText>{error}</ErrorText>}
      {data === null && !error && <SkeletonList rows={3} />}
      {data !== null && tab === 'incomes' && (
        <Section
          footer={data.incomes.length === 0 ? 'В этом месяце поступлений не было.' : undefined}
        >
          {data.incomes.map((income, index) => (
            <Row
              key={index}
              leading={<PersonAvatar person={income.client} />}
              title={fullName(income.client)}
              subtitle={`${dayShort(income.day)} · ${income.kind === 'one_off' ? `разовое, ${income.label}` : income.label}`}
              value={rubles(income.amount)}
            />
          ))}
        </Section>
      )}
      {data !== null && tab === 'clients' && (
        <Section
          footer={
            data.clients.length === 0
              ? 'В этом месяце никто не занимался и не платил.'
              : 'Получено и отработано за месяц по каждому клиенту.'
          }
        >
          {data.clients.map((item) => (
            <Row
              key={item.client.id}
              leading={<PersonAvatar person={item.client} />}
              title={fullName(item.client)}
              subtitle={`${plural(item.sessions, 'занятие', 'занятия', 'занятий')} · отработано ${rubles(item.worked)}`}
              value={rubles(item.received)}
            />
          ))}
        </Section>
      )}
    </Screen>
  )
}

function Forecast({ onBack }: { onBack: () => void }) {
  const [data, setData] = useState<FinanceForecast | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchFinanceForecast()
      .then(setData)
      .catch((err: unknown) => setError(String(err)))
  }, [])

  return (
    <Screen
      title="Прогноз"
      subtitle="На 30 дней вперёд, по тому, что уже есть в расписании и блоках"
      onBack={onBack}
    >
      {error && <ErrorText>{error}</ErrorText>}
      {data === null && !error && <SkeletonList rows={3} />}
      {data !== null && (
        <>
          <div className="money-hero">
            <span className="money-hero-kicker">Ожидаем за {data.days} дней</span>
            <span className="money-hero-amount">≈ {rubles(data.total)}</span>
          </div>
          <Section title="Ждём доплат">
            {data.dues.length === 0 && <Row title="Все блоки оплачены" tone="muted" />}
            {data.dues.map((due) => (
              <Row
                key={due.package_id}
                leading={<PersonAvatar person={due.client} />}
                title={fullName(due.client)}
                subtitle={`${due.package_name} · внесено ${rubles(due.paid)} из ${rubles(due.price)}`}
                value={rubles(due.due)}
              />
            ))}
          </Section>
          <Section
            title="Скоро закончится блок"
            footer="Оценка продления — цена текущего блока клиента."
          >
            {data.renewals.length === 0 && <Row title="Пока никому не пора" tone="muted" />}
            {data.renewals.map((renewal) => (
              <Row
                key={renewal.package_id}
                leading={<PersonAvatar person={renewal.client} />}
                title={fullName(renewal.client)}
                subtitle={`${renewal.package_name} · осталось ${renewal.left} из ${renewal.sessions_count}`}
                value={`≈ ${rubles(renewal.price)}`}
              />
            ))}
          </Section>
          <Section
            title="Разовые занятия"
            footer="Будущие записи без блока, по цене услуги. Занятия из оплаченных блоков новых денег не приносят."
          >
            <Row
              title={plural(data.one_off_count, 'запись', 'записи', 'записей')}
              value={rubles(data.one_off)}
            />
          </Section>
        </>
      )}
    </Screen>
  )
}
