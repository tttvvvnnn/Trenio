import type { Package, PackageSession, PlannedSession } from '../api'
import {
  ATTENDANCE_SHORT,
  PACKAGE_STATUS,
  dateTime,
  dayTitle,
  longDate,
  packageLine,
  plural,
  rubles,
  sessionsLeft,
  shortDate,
} from '../format'
import { Row, Section } from './kit'

type Props = {
  pkg: Package
  // Тренеру строки занятий нажимаются: открыть запись, исправить или отметить занятие
  onSession?: (session: PackageSession) => void
  onPlanned?: (planned: PlannedSession) => void
  onFree?: () => void
}

/** Карточка блока: деньги и занятия по порядку. Общая для тренера и клиента. */
export default function PackageSummary({ pkg, onSession, onPlanned, onFree }: Props) {
  const payments = pkg.payments.map((p) => `${shortDate(p.paid_on)} — ${rubles(p.amount)}`)
  const timezone = pkg.trainer.timezone
  const now = new Date()
  const free = Math.max(pkg.sessions_count - pkg.used - pkg.planned.length, 0)
  const active = pkg.status === 'active'
  const footer = [
    active ? `Осталось ${plural(pkg.left, 'занятие', 'занятия', 'занятий')}.` : null,
    active && pkg.planned.length > 0 && free === 0
      ? 'Все оставшиеся занятия уже заняты записями: следующие записи будут без блока.'
      : null,
  ]
    .filter(Boolean)
    .join(' ')
  return (
    <>
      <Section>
        <Row title="Статус" after={<PackageBadge pkg={pkg} />} />
        <Row title="Услуга" value={pkg.service?.name ?? 'Любая'} />
        <Row title="Стоимость" value={rubles(pkg.price)} />
        <Row
          title="Внесено"
          subtitle={payments.length > 0 ? payments.join(' · ') : undefined}
          value={rubles(pkg.paid)}
        />
        <Row
          title={pkg.due > 0 ? 'Осталось доплатить' : 'Оплачено полностью'}
          value={pkg.due > 0 ? rubles(pkg.due) : undefined}
        />
        <Row title="Куплен" value={longDate(pkg.purchased_on)} />
        <Row
          title="Действует"
          value={pkg.valid_until ? `до ${longDate(pkg.valid_until)}` : 'бессрочно'}
        />
      </Section>
      <Section title={`Пройдено ${pkg.used} из ${pkg.sessions_count}`} footer={footer || undefined}>
        {pkg.sessions.map((session) => (
          <Row
            key={`s${session.id}`}
            title={`Занятие ${session.number}`}
            subtitle={[
              ATTENDANCE_SHORT[session.status],
              dayTitle(session.day),
              session.booking_id === null ? 'без записи' : null,
            ]
              .filter(Boolean)
              .join(' · ')}
            icon={
              session.status === 'attended'
                ? { name: 'check', color: 'var(--c-success)' }
                : { name: 'minus', color: 'var(--c-warning)' }
            }
            chevron={onSession !== undefined}
            onClick={onSession && (() => onSession(session))}
          />
        ))}
        {pkg.planned.map((planned) => {
          // Прошедшая запись ждёт отметки тренера, будущая — запланирована
          const past = new Date(planned.starts_at) <= now
          return (
            <Row
              key={`p${planned.booking_id}`}
              title={`Занятие ${planned.number}`}
              subtitle={`${past ? 'не отмечена' : 'запланирована'} · ${dateTime(planned.starts_at, timezone)}`}
              icon={{ name: 'clock', color: past ? 'var(--c-violet)' : 'var(--c-accent)' }}
              chevron={onPlanned !== undefined}
              onClick={onPlanned && (() => onPlanned(planned))}
            />
          )
        })}
        {active &&
          Array.from({ length: free }, (_, index) => {
            const number = pkg.used + pkg.planned.length + index + 1
            return (
              <Row
                key={`f${number}`}
                title={`Занятие ${number}`}
                subtitle={onFree ? 'свободно · нажмите, чтобы отметить без записи' : 'свободно'}
                icon={{ name: 'plus', color: 'var(--c-hint)' }}
                tone="muted"
                onClick={onFree}
              />
            )
          })}
      </Section>
    </>
  )
}

export function PackageBadge({ pkg }: { pkg: Package }) {
  if (pkg.ending_soon) {
    return <span className="badge warning">{sessionsLeft(pkg.left)}</span>
  }
  return (
    <span className={pkg.status === 'active' ? 'badge success' : 'badge'}>
      {PACKAGE_STATUS[pkg.status]}
    </span>
  )
}

/** Действующий блок: сколько пройдено полоской, оплата и срок. */
export function BlockCard({
  pkg,
  title,
  onClick,
}: {
  pkg: Package
  // По умолчанию название блока
  title?: string
  onClick: () => void
}) {
  const done = Math.min(pkg.used / pkg.sessions_count, 1)
  return (
    <button type="button" className="block-card" onClick={onClick}>
      <span className="block-card-top">
        <strong>{title ?? pkg.name}</strong>
        <PackageBadge pkg={pkg} />
      </span>
      <span className="block-card-line">{packageLine(pkg)}</span>
      <span className="block-bar" aria-hidden="true">
        <i style={{ width: `${Math.max(done * 100, 2)}%` }} />
      </span>
    </button>
  )
}
