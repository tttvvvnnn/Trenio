import { haptic } from '../telegram'
import BrandMark from './BrandMark'
import { PageHeader, Row, Section } from './kit'

type Props = {
  name: string
  // true — профиль клиента, false — профиль тренера
  onChoose: (clientMode: boolean) => void
}

// Выбор профиля при входе для тех, кто одновременно тренер и клиент
export default function RolePicker({ name, onChoose }: Props) {
  function choose(clientMode: boolean) {
    haptic.select()
    onChoose(clientMode)
  }

  return (
    <>
      <div className="role-picker-mark">
        <BrandMark size={56} />
      </div>
      <PageHeader title={`Привет, ${name}!`} subtitle="В какой профиль войти?" />
      <Section>
        <Row
          title="Тренер"
          subtitle="Расписание, записи и клиенты"
          icon={{ name: 'user', color: 'var(--c-violet)' }}
          chevron
          onClick={() => choose(false)}
        />
        <Row
          title="Клиент"
          subtitle="Запись к своим тренерам"
          icon={{ name: 'calendar', color: 'var(--c-accent)' }}
          chevron
          onClick={() => choose(true)}
        />
      </Section>
    </>
  )
}
