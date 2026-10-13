import type { Package, PackageSession } from '../api'
import { PACKAGE_STATUS, longDate, plural, rubles, sessionsLeft, shortDate } from '../format'
import { Row, Section } from './kit'

type Props = {
  pkg: Package
  // Тренер нажимает на занятие, отмеченное вручную, чтобы снять его
  onSession?: (session: PackageSession) => void
}

/** Карточка блока: деньги и пронумерованные занятия. Общая для тренера и клиента. */
export default function PackageSummary({ pkg, onSession }: Props) {
  const cells = Array.from({ length: pkg.sessions_count }, (_, index) => pkg.sessions[index])
  const payments = pkg.payments.map((p) => `${shortDate(p.paid_on)} — ${rubles(p.amount)}`)
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
      <Section
        title={`Пройдено ${pkg.used} из ${pkg.sessions_count}`}
        footer={[
          '✓ прошла, ✗ пропуск со списанием.',
          pkg.status === 'active'
            ? `Осталось ${plural(pkg.left, 'занятие', 'занятия', 'занятий')}.`
            : null,
        ]
          .filter(Boolean)
          .join(' ')}
      >
        <div className="visits">
          {cells.map((session, index) => {
            if (!session) {
              return (
                <div key={`free-${index}`} className="visit free">
                  <strong>{index + 1}</strong>
                </div>
              )
            }
            const label = session.status === 'attended' ? '✓' : '✗'
            const content = (
              <>
                <strong>{session.number}</strong>
                <span>
                  {label} {shortDate(session.day)}
                </span>
              </>
            )
            // Занятия, списанные за запись, снимаются в самой записи
            return onSession && session.booking_id === null ? (
              <button
                key={session.id}
                type="button"
                className={`visit ${session.status}`}
                onClick={() => onSession(session)}
              >
                {content}
              </button>
            ) : (
              <div key={session.id} className={`visit ${session.status}`}>
                {content}
              </div>
            )
          })}
        </div>
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
