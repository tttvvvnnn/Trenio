import type { Section } from '../sections'
import { PageTitle } from './common'

const PLANNED: Partial<Record<Section, { title: string; items: string[] }>> = {
  broadcasts: {
    title: 'Рассылки',
    items: ['сообщение всем тренерам или сегменту', 'предпросмотр и тест себе', 'доставлено, нажали кнопку, ответили'],
  },
  plans: {
    title: 'Тарифы и промо',
    items: ['цена Pro, пробный период и лимит бесплатного тарифа', 'промокоды и личные скидки', 'промо TVPN'],
  },
  support: {
    title: 'Обращения',
    items: ['вопросы и отзывы тренеров из бота', 'ответ прямо из админки', 'подсказки из данных: например, клиент заблокировал бота'],
  },
}

export default function Soon({ section }: { section: Section }) {
  const plan = PLANNED[section]
  if (!plan) return null
  return (
    <>
      <PageTitle sub="раздел в работе" title={plan.title} />
      <section className="glass tile span-12">
        <h2>Скоро здесь</h2>
        <ul style={{ margin: 0, paddingLeft: 20, display: 'flex', flexDirection: 'column', gap: 6 }}>
          {plan.items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>
    </>
  )
}
