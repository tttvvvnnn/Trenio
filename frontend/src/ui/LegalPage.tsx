import { useEffect } from 'react'

import type { LegalDoc } from '../api'
import { ErrorText, PageHeader, SkeletonList } from './kit'
import { LEGAL_TITLES, useLegal } from '../legal'
import { LegalText } from './Privacy'

/** Публичная страница документа: открывается в браузере без Telegram и без входа. */
export default function LegalPage({ doc }: { doc: LegalDoc }) {
  const [policy, error] = useLegal(doc)

  useEffect(() => {
    document.title = `${LEGAL_TITLES[doc]} · Trenio`
    // Вне Telegram тему берём из системы
    const dark = window.matchMedia('(prefers-color-scheme: dark)').matches
    document.documentElement.dataset.scheme = dark ? 'dark' : 'light'
  }, [doc])

  const other: LegalDoc = doc === 'terms' ? 'privacy' : 'terms'
  return (
    <main className="app legal-page">
      <PageHeader brand title={LEGAL_TITLES[doc]} />
      <nav className="legal-page-nav">
        <a href={`/${other}`}>{LEGAL_TITLES[other]}</a>
      </nav>
      {policy ? (
        <section className="section">
          <div className="group">
            <LegalText text={policy.text} />
          </div>
        </section>
      ) : (
        !error && <SkeletonList rows={6} />
      )}
      {error && <ErrorText>{error}</ErrorText>}
    </main>
  )
}
