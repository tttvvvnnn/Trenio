import { useEffect, type ReactNode } from 'react'

import { PageHeader } from './kit'
import { BackButton } from './native'

type Props = {
  title: string
  subtitle?: ReactNode
  // Фото человека слева от заголовка
  avatar?: ReactNode
  onBack: () => void
  // Своя шапка вместо заголовка, например сводка записи. title остаётся подписью для экранного диктора
  header?: ReactNode
  children: ReactNode
}

// Сколько экранов открыто сейчас. Экраны вложены и могут закрыться одним махом
// (отменили запись — закрылись и форма, и детали), а React снимает их в любом порядке.
// Поэтому не запоминаем «как было» у каждого, а считаем: прокрутка вернётся с последним
let openScreens = 0

/** Вложенный экран поверх вкладки: форма или подробности, с кнопкой «Назад». */
export default function Screen({ title, subtitle, avatar, onBack, header, children }: Props) {
  // Страница под экраном не должна прокручиваться вместе с ним
  useEffect(() => {
    openScreens += 1
    document.body.style.overflow = 'hidden'
    return () => {
      openScreens -= 1
      if (openScreens === 0) document.body.style.overflow = ''
    }
  }, [])

  return (
    <div className="screen-overlay" role="dialog" aria-modal="true" aria-label={title}>
      <BackButton onClick={onBack} />
      {header ?? <PageHeader title={title} subtitle={subtitle} leading={avatar} />}
      {children}
    </div>
  )
}
