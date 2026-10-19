import { useEffect, useState } from 'react'

import { errorText, fetchLegal, type LegalDoc, type Policy } from './api'

export const LEGAL_TITLES: Record<LegalDoc, string> = {
  terms: 'Пользовательское соглашение',
  privacy: 'Политика конфиденциальности',
}

/** Документ по адресу /privacy или /terms; null — это не страница документа. */
export function legalDocFromPath(path: string): LegalDoc | null {
  const name = path.replace(/\/+$/, '')
  if (name === '/privacy') return 'privacy'
  if (name === '/terms') return 'terms'
  return null
}

export function useLegal(doc: LegalDoc): [Policy | null, string | null] {
  const [policy, setPolicy] = useState<Policy | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    fetchLegal(doc)
      .then(setPolicy)
      .catch((err: unknown) => setError(errorText(err)))
  }, [doc])
  return [policy, error]
}
