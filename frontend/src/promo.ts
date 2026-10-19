import { useEffect, useState } from 'react'

import { fetchPromo, type Promo } from './api'
import { useRefreshKey } from './sync'

/** Промо от автора Trenio; null — выключено или не загрузилось. */
export function usePromo(): Promo | null {
  const [promo, setPromo] = useState<Promo | null>(null)
  const refreshKey = useRefreshKey()

  useEffect(() => {
    fetchPromo()
      .then(setPromo)
      .catch(() => setPromo(null))
  }, [refreshKey])

  return promo
}
