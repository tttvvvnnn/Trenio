export type Section =
  | 'summary'
  | 'trainers'
  | 'clients'
  | 'money'
  | 'broadcasts'
  | 'plans'
  | 'support'
  | 'system'

export const SECTIONS: { id: Section; label: string }[] = [
  { id: 'summary', label: 'Сводка' },
  { id: 'trainers', label: 'Тренеры' },
  { id: 'clients', label: 'Клиенты' },
  { id: 'money', label: 'Деньги' },
  { id: 'broadcasts', label: 'Рассылки' },
  { id: 'plans', label: 'Тарифы' },
  { id: 'support', label: 'Обращения' },
  { id: 'system', label: 'Система' },
]
