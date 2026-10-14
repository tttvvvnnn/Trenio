import { useId, type ReactNode } from 'react'

import { haptic } from '../telegram'
import Icon, { type IconName } from './icons'

type SectionProps = {
  title?: ReactNode
  footer?: ReactNode
  children: ReactNode
}

export function Section({ title, footer, children }: SectionProps) {
  return (
    <section className="section">
      {title && <h2 className="section-title">{title}</h2>}
      <div className="group">{children}</div>
      {footer && <p className="section-footer">{footer}</p>}
    </section>
  )
}

type RowProps = {
  title: ReactNode
  subtitle?: ReactNode
  // Иконка на цветной плашке слева, цвет — CSS-значение
  icon?: { name: IconName; color: string }
  value?: ReactNode
  // Бейдж или галочка справа внутри нажимаемой области
  badge?: ReactNode
  // Элемент справа вне нажимаемой области: переключатель, степпер
  after?: ReactNode
  chevron?: boolean
  tone?: 'muted' | 'accent' | 'destructive'
  // Текст по центру, как у кнопки-действия
  centered?: boolean
  onClick?: () => void
}

export function Row({
  title,
  subtitle,
  icon,
  value,
  badge,
  after,
  chevron,
  tone,
  centered,
  onClick,
}: RowProps) {
  const content = (
    <>
      {icon && (
        <span className="row-icon" style={{ background: icon.color }}>
          <Icon name={icon.name} />
        </span>
      )}
      <span className="row-text">
        <span className="row-title">{title}</span>
        {subtitle && <span className="row-subtitle">{subtitle}</span>}
      </span>
      {value !== undefined && <span className="row-value">{value}</span>}
      {badge}
      {chevron && <Icon name="chevronRight" className="row-chevron" />}
    </>
  )
  const className = ['row', icon && 'with-icon', tone, centered && 'row-centered']
    .filter(Boolean)
    .join(' ')
  return (
    <div className={className}>
      {onClick ? (
        <button type="button" className="row-main" onClick={onClick}>
          {content}
        </button>
      ) : (
        <div className="row-main">{content}</div>
      )}
      {after}
    </div>
  )
}

type AddRowProps = {
  title: string
  onClick: () => void
}

export function AddRow({ title, onClick }: AddRowProps) {
  return (
    <div className="row accent">
      <button type="button" className="row-main" onClick={onClick}>
        <Icon name="plus" />
        <span className="row-text">{title}</span>
      </button>
    </div>
  )
}

type SwitchProps = {
  checked: boolean
  onChange: (checked: boolean) => void
  label: string
  disabled?: boolean
}

export function Switch({ checked, onChange, label, disabled }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      className="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => {
        haptic.tap()
        onChange(!checked)
      }}
    />
  )
}

type SwitchRowProps = SwitchProps & {
  icon?: RowProps['icon']
  subtitle?: ReactNode
}

export function SwitchRow({ label, icon, subtitle, ...props }: SwitchRowProps) {
  return (
    <Row
      title={label}
      subtitle={subtitle}
      icon={icon}
      after={<Switch label={label} {...props} />}
    />
  )
}

type StepperProps = {
  value: number
  // Допустимые значения по возрастанию
  options: number[]
  onChange: (value: number) => void
  format?: (value: number) => string
  label: string
}

export function Stepper({ value, options, onChange, format = String, label }: StepperProps) {
  // Значение не из списка встаёт между ближайшими соседями
  const smaller = options.filter((option) => option < value)
  const lower = smaller[smaller.length - 1]
  const higher = options.find((option) => option > value)
  function step(next: number | undefined) {
    if (next === undefined) return
    haptic.tap()
    onChange(next)
  }
  return (
    <div className="stepper" role="group" aria-label={label}>
      <button
        type="button"
        aria-label="Меньше"
        disabled={lower === undefined}
        onClick={() => step(lower)}
      >
        <Icon name="minus" />
      </button>
      <output aria-live="polite">{format(value)}</output>
      <button
        type="button"
        aria-label="Больше"
        disabled={higher === undefined}
        onClick={() => step(higher)}
      >
        <Icon name="plus" />
      </button>
    </div>
  )
}

type ChoiceProps<T extends string | number> = {
  value: T
  options: readonly (readonly [T, string])[]
  onChange: (value: T) => void
  label: string
}

export function Chips<T extends string | number>({
  value,
  options,
  onChange,
  label,
}: ChoiceProps<T>) {
  return (
    <div className="chips" role="radiogroup" aria-label={label}>
      {options.map(([option, title]) => (
        <button
          key={option}
          type="button"
          role="radio"
          className="chip"
          aria-checked={option === value}
          onClick={() => {
            haptic.select()
            onChange(option)
          }}
        >
          {title}
        </button>
      ))}
    </div>
  )
}

type MultiChipsProps<T extends string | number> = {
  values: readonly T[]
  options: readonly (readonly [T, string])[]
  onToggle: (value: T) => void
  label: string
}

// Несколько вариантов сразу, например «за сутки» и «за 2 часа»
export function MultiChips<T extends string | number>({
  values,
  options,
  onToggle,
  label,
}: MultiChipsProps<T>) {
  return (
    <div className="chips" role="group" aria-label={label}>
      {options.map(([option, title]) => (
        <button
          key={option}
          type="button"
          role="checkbox"
          className="chip"
          aria-checked={values.includes(option)}
          onClick={() => {
            haptic.select()
            onToggle(option)
          }}
        >
          {title}
        </button>
      ))}
    </div>
  )
}

export function Segmented<T extends string | number>({
  value,
  options,
  onChange,
  label,
}: ChoiceProps<T>) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map(([option, title]) => (
        <button
          key={option}
          type="button"
          role="radio"
          aria-checked={option === value}
          onClick={() => {
            if (option === value) return
            haptic.select()
            onChange(option)
          }}
        >
          {title}
        </button>
      ))}
    </div>
  )
}

type TextFieldProps = {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  footer?: ReactNode
  maxLength?: number
  inputMode?: 'text' | 'numeric'
  required?: boolean
}

// Поле на всю ширину: подпись над секцией, как в настройках Telegram
export function TextField({ label, footer, onChange, ...input }: TextFieldProps) {
  const id = useId()
  return (
    <section className="section">
      <label className="section-title" htmlFor={id}>
        {label}
      </label>
      <div className="group">
        <input
          id={id}
          className="field-input"
          onChange={(event) => onChange(event.target.value)}
          {...input}
        />
      </div>
      {footer && <p className="section-footer">{footer}</p>}
    </section>
  )
}

type InlineFieldProps = {
  label: string
  icon?: RowProps['icon']
  children: (id: string) => ReactNode
}

// Строка «подпись слева, поле справа»
export function InlineField({ label, icon, children }: InlineFieldProps) {
  const id = useId()
  return (
    <div className={icon ? 'row with-icon' : 'row'}>
      {icon && (
        <span className="row-icon" style={{ background: icon.color }}>
          <Icon name={icon.name} />
        </span>
      )}
      <label className="row-label" htmlFor={id}>
        {label}
      </label>
      {children(id)}
    </div>
  )
}

type EmptyStateProps = {
  icon: IconName
  title: string
  text: string
  action?: { label: string; onClick: () => void }
}

export function EmptyState({ icon, title, text, action }: EmptyStateProps) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Icon name={icon} />
      </div>
      <h2>{title}</h2>
      <p>{text}</p>
      {action && (
        <button type="button" className="button" onClick={action.onClick}>
          {action.label}
        </button>
      )}
    </div>
  )
}

// Заглушка списка, пока данные грузятся
export function SkeletonList({ rows = 3 }: { rows?: number }) {
  return (
    <div className="section" aria-busy="true" aria-label="Загрузка">
      <div className="group">
        {Array.from({ length: rows }, (_, index) => (
          <div key={index} className="row">
            <div className="row-main">
              <span className="row-text">
                <span className="skeleton" style={{ width: `${55 - index * 8}%` }} />
                <span className="skeleton" style={{ width: '35%', marginTop: 8, height: 12 }} />
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function ErrorText({ children }: { children: ReactNode }) {
  return (
    <p className="error" role="alert">
      <Icon name="alert" />
      <span>{children}</span>
    </p>
  )
}

type PageHeaderProps = {
  title: string
  subtitle?: ReactNode
}

export function PageHeader({ title, subtitle }: PageHeaderProps) {
  return (
    <header className="page-header">
      <h1>{title}</h1>
      {subtitle && <p>{subtitle}</p>}
    </header>
  )
}
