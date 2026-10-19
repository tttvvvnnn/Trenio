import { haptic } from '../telegram'
import BrandMark from './BrandMark'
import { PageHeader, Row, Section } from './kit'

export type Mode = 'trainer' | 'client' | 'admin'

type Props = {
  name: string
  // Какие профили есть у человека
  trainer: boolean
  client: boolean
  admin: boolean
  onChoose: (mode: Mode) => void
}

// Выбор профиля при входе для тех, у кого их несколько: тренер, клиент, админ
export default function RolePicker({ name, trainer, client, admin, onChoose }: Props) {
  function choose(mode: Mode) {
    haptic.select()
    onChoose(mode)
  }

  return (
    <>
      <div className="role-picker-mark">
        <BrandMark size={56} />
      </div>
      <PageHeader title={`Привет, ${name}!`} subtitle="В какой профиль войти?" />
      <Section>
        {trainer && (
          <Row
            title="Тренер"
            subtitle="Расписание, записи и клиенты"
            icon={{ name: 'user', color: 'var(--c-violet)' }}
            chevron
            onClick={() => choose('trainer')}
          />
        )}
        {client && (
          <Row
            title="Клиент"
            subtitle="Запись к своим тренерам"
            icon={{ name: 'calendar', color: 'var(--c-accent)' }}
            chevron
            onClick={() => choose('client')}
          />
        )}
        {admin && (
          <Row
            title="Админ-панель"
            subtitle="Как идут дела у Trenio"
            icon={{ name: 'chart', color: 'var(--c-planned)' }}
            chevron
            onClick={() => choose('admin')}
          />
        )}
      </Section>
    </>
  )
}
