import { useEffect, useState } from 'react'

import {
  errorText,
  fetchMyPackages,
  fetchMyProgress,
  type Package,
  type TrainerProgress,
} from '../api'
import { packageLine } from '../format'
import { EmptyState, ErrorText, Row, Section, SkeletonList } from '../ui/kit'
import PackageSummary, { BlockCard, PackageBadge } from '../ui/PackageSummary'
import ProgressList from '../ui/Progress'
import Screen from '../ui/Screen'
import { useRefreshKey } from '../sync'

function usePackages(): [Package[] | null, string | null] {
  const [packages, setPackages] = useState<Package[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const refreshKey = useRefreshKey()
  useEffect(() => {
    fetchMyPackages()
      .then(setPackages)
      .catch((err: unknown) => setError(errorText(err)))
  }, [refreshKey])
  return [packages, error]
}

// Имя тренера рядом с блоком нужно, только если тренеров несколько
function blockTitle(pkg: Package, packages: Package[]): string {
  const many = new Set(packages.map((item) => item.trainer.id)).size > 1
  return many ? `${pkg.name} · ${pkg.trainer.display_name}` : pkg.name
}

function PackageScreen({ pkg, onBack }: { pkg: Package; onBack: () => void }) {
  return (
    <Screen title={pkg.name} subtitle={pkg.trainer.display_name} onBack={onBack}>
      <PackageSummary pkg={pkg} />
    </Screen>
  )
}

/** Действующие блоки карточками с полоской: сколько пройдено и оплачено. */
export function ActiveBlocks() {
  const [packages] = usePackages()
  const [opened, setOpened] = useState<Package | null>(null)
  if (packages === null) return null
  const current = packages.filter((pkg) => pkg.status === 'active')
  // Тренеры, у которых блок закончился и нового нет
  const ended = [...new Set(packages.map((pkg) => pkg.trainer.id))].filter(
    (id) => !current.some((pkg) => pkg.trainer.id === id),
  )
  return (
    <>
      {ended.length > 0 && (
        <p className="card-hint pending">
          Блок закончился. Записываться можно и дальше, но занятия будут без блока: о новом блоке
          договоритесь с тренером.
        </p>
      )}
      {current.length > 0 && (
        <Section>
          {current.map((pkg) => (
            <BlockCard
              key={pkg.id}
              pkg={pkg}
              title={blockTitle(pkg, packages)}
              onClick={() => setOpened(pkg)}
            />
          ))}
        </Section>
      )}
      {opened && <PackageScreen pkg={opened} onBack={() => setOpened(null)} />}
    </>
  )
}

/** Закончившиеся блоки: внизу «Истории». */
export function PastBlocks() {
  const [packages, error] = usePackages()
  const [opened, setOpened] = useState<Package | null>(null)
  if (packages === null) return error ? <ErrorText>{error}</ErrorText> : null
  const past = packages.filter((pkg) => pkg.status !== 'active')
  if (past.length === 0) return null
  return (
    <>
      <Section title="Прошлые блоки">
        {past.map((pkg) => (
          <Row
            key={pkg.id}
            title={blockTitle(pkg, packages)}
            subtitle={packageLine(pkg)}
            tone="muted"
            onClick={() => setOpened(pkg)}
            badge={<PackageBadge pkg={pkg} />}
          />
        ))}
      </Section>
      {opened && <PackageScreen pkg={opened} onBack={() => setOpened(null)} />}
    </>
  )
}

/** Замеры у каждого тренера, только чтение. */
export function MyProgress() {
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
