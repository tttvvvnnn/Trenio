import Icon from './icons'

type Props = {
  text: string
  hint?: string
  onClose: () => void
}

/** Плашка сверху, когда кнопка из уведомления ведёт на то, чего уже нет. */
export default function LinkNotice({ text, hint, onClose }: Props) {
  return (
    <div className="offline-banner link-notice" role="status">
      <Icon name="alert" />
      <span>
        {text}
        {hint && <small>{hint}</small>}
      </span>
      <button type="button" onClick={onClose}>
        Понятно
      </button>
    </div>
  )
}
