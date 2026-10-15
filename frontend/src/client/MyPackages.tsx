import { useEffect, useState } from 'react'

import {
  errorText,
  fetchMyPackages,
  fetchMyProgress,
  type Package,
  type TrainerProgress,
} from '../api'
import { packageLine } from '../format'
import { EmptyState, ErrorText, PageHeader, Row, Section, Segmented, SkeletonList } from '../ui/kit'
import PackageSummary, { PackageBadge } from '../ui/PackageSummary'
import ProgressList from '../ui/Progress'
import Screen from '../ui/Screen'
import { useRefreshKey } from '../sync'

type Tab = 'packages' | 'progress'

/** Блоки клиента и, на второй вкладке, замеры, которые записал тренер. */
export default function MyPackages() {
  const [tab, setTab] = useState<Tab>('packages')
  return (
    <>
      <PageHeader title="Блоки" subtitle="Занятия и оплаты по вашим блокам." />
      <Segmented
        label="Что показать"
        value={tab}
        options={[
          ['packages', 'Блоки'],
          ['progress', 'Прогресс'],
        ]}
        onChange={setTab}
      />
      {tab === 'packages' ? <Packages /> : <MyProgress />}
    </>
  )
}

/** Блоки клиента: сколько занятий пройдено и осталось, сколько оплачено. */
function Packages() {
  const [packages, setPackages] = useState<Package[] | null>(null)
  const [opened, setOpened] = useState<Package | null>(null)
  const [error, setError] = useState<string | null>(null)
  const refreshKey = useRefreshKey()

  useEffect(() => {
    fetchMyPackages()
      .then(setPackages)
      .catch((err: unknown) => setError(errorText(err)))
  }, [refreshKey])

  if (packages === null) {
    return error ? <ErrorText>{error}</ErrorText> : <SkeletonList rows={2} />
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

/** Замеры у каждого тренера, только чтение. */
function MyProgress() {
  const [progress, setProgress] = useState<TrainerProgress[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const refreshKey = useRefreshKey()

  useEffect(() => {
    fetchMyProgress()
      .then(setProgress)
      .catch((err: unknown) => setError(errorText(err)))
  }, [refreshKey])

  if (progress === null) {
    return error ? <ErrorText>{error}</ErrorText> : <SkeletonList rows={2} />
  }
  if (progress.length === 0) {
    return (
      <EmptyState
        icon="chart"
        title="Пока нет замеров"
        text="Когда тренер запишет ваш вес или обхваты, здесь появятся графики."
      />
    )
  }
  // Имя тренера в заголовке нужно, только если тренеров несколько
  const manyTrainers = progress.length > 1
  return (
    <>
      {progress.map((item) => (
        <ProgressList
          key={item.trainer_id}
          series={
            manyTrainers
              ? item.series.map((one) => ({ ...one, label: `${one.label} · ${item.trainer_name}` }))
              : item.series
          }
        />
      ))}
    </>
  )
}
