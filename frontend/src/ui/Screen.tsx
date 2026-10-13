import { useEffect, type ReactNode } from 'react'

import { PageHeader } from './kit'
import { BackButton } from './native'

type Props = {
  title: string
  subtitle?: ReactNode
  onBack: () => void
  children: ReactNode
}

/** Вложенный экран поверх вкладки: форма или подробности, с кнопкой «Назад». */
export default function Screen({ title, subtitle, onBack, children }: Props) {
  // Страница под экраном не должна прокручиваться вместе с ним
  useEffect(() => {
    const { overflow } = document.body.style
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = overflow
    }
  }, [])

  return (
    <div className="screen-overlay" role="dialog" aria-modal="true" aria-label={title}>
      <BackButton onClick={onBack} />
      <PageHeader title={title} subtitle={subtitle} />
      {children}
    </div>
  )
}
