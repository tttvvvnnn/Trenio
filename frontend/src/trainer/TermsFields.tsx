import { duration } from '../format'
import { InlineField, Row, Section, Stepper, SwitchRow } from '../ui/kit'

export type TermsValue = {
  durationMin: number
  // Цена разового занятия строкой, как её вводят; пусто — цены нет
  price: string
  noPackage: boolean
}

type Props = {
  value: TermsValue
  onChange: (value: TermsValue) => void
  // Групповое занятие: длительность общая, её не поменять
  group: boolean
  // Длительность уже не поменять: занятие прошло или отменено
  durationLocked?: boolean
  footer?: string
}

// Длительность шагом 15 минут, от 15 минут до 4 часов
const DURATIONS = Array.from({ length: 16 }, (_, i) => (i + 1) * 15)

/** Условия одного занятия: длительность, цена разового, списывать ли из блока. */
export default function TermsFields({ value, onChange, group, durationLocked, footer }: Props) {
  const fixed = group || durationLocked
  return (
    <Section title="Условия этого занятия" footer={footer}>
      <Row
        title="Длительность"
        subtitle={group ? 'У группового занятия общая' : undefined}
        value={fixed ? duration(value.durationMin) : undefined}
        after={
          fixed ? undefined : (
            <Stepper
              label="Длительность"
              value={value.durationMin}
              options={DURATIONS}
              format={duration}
              onChange={(durationMin) => onChange({ ...value, durationMin })}
            />
          )
        }
      />
      <InlineField label="Цена разового, ₽">
        {(id) => (
          <input
            id={id}
            className="row-input"
            inputMode="numeric"
            placeholder="не указана"
            value={value.price}
            onChange={(event) =>
              onChange({ ...value, price: event.target.value.replace(/[^\d\s]/g, '') })
            }
          />
        )}
      </InlineField>
      <SwitchRow
        label="Не списывать из блока"
        subtitle="Оплата отдельно, даже если у клиента есть блок"
        checked={value.noPackage}
        onChange={(noPackage) => onChange({ ...value, noPackage })}
      />
    </Section>
  )
}
