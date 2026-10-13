import { useEffect, useState } from 'react'

import { fetchMyPackages, type Package } from '../api'
import { packageLine } from '../format'
import { EmptyState, ErrorText, PageHeader, Row, Section, SkeletonList } from '../ui/kit'
import PackageSummary, { PackageBadge } from '../ui/PackageSummary'
import Screen from '../ui/Screen'

/** Блоки клиента: сколько занятий пройдено и осталось, сколько оплачено. */
export default function MyPackages() {
  const [packages, setPackages] = useState<Package[] | null>(null)
  const [opened, setOpened] = useState<Package | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchMyPackages()
      .then(setPackages)
      .catch((err: unknown) => setError(String(err)))
  }, [])

  const header = <PageHeader title="Блоки" subtitle="Занятия и оплаты по вашим блокам." />
  if (packages === null) {
    return (
      <>
        {header}
        {error ? <ErrorText>{error}</ErrorText> : <SkeletonList rows={2} />}
      </>
    )
  }
  if (packages.length === 0) {
    return (
      <EmptyState
        icon="ticket"
        title="Пока нет блоков"
        text="Когда тренер оформит вам блок занятий, здесь будет видно, сколько пройдено и оплачено."
      />
    )
  }

  const current = packages.filter((pkg) => pkg.status === 'active')
  // По тренерам, у которых блок закончился и нового нет
  const ended = [...new Set(packages.map((pkg) => pkg.trainer.id))].filter(
    (id) => !current.some((pkg) => pkg.trainer.id === id),
  )
  const past = packages.filter((pkg) => pkg.status !== 'active')
  // Имя тренера показываем, только если тренеров несколько
  const manyTrainers = new Set(packages.map((pkg) => pkg.trainer.id)).size > 1
  const row = (pkg: Package) => (
    <Row
      key={pkg.id}
      title={manyTrainers ? `${pkg.name} · ${pkg.trainer.display_name}` : pkg.name}
      subtitle={packageLine(pkg)}
      tone={pkg.status === 'active' ? undefined : 'muted'}
      onClick={() => setOpened(pkg)}
      badge={<PackageBadge pkg={pkg} />}
    />
  )

  return (
    <>
      {header}
      {ended.length > 0 && (
        <p className="card-hint pending">
          Блок закончился. Записываться можно и дальше, но занятия будут без блока: о новом блоке
          договоритесь с тренером.
        </p>
      )}
      {current.length > 0 && <Section title="Действующие">{current.map(row)}</Section>}
      {past.length > 0 && <Section title="Завершённые">{past.map(row)}</Section>}
      {opened && (
        <Screen
          title={opened.name}
          subtitle={opened.trainer.display_name}
          onBack={() => setOpened(null)}
        >
          <PackageSummary pkg={opened} />
        </Screen>
      )}
    </>
  )
}
