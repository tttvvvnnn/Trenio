import { useId } from 'react'

type Props = {
  value: string
  onChange: (value: string) => void
  placeholder: string
  footer?: string
}

// Как на сервере: пара фраз, а не письмо
export const MAX_COMMENT = 500

/** Необязательный комментарий к отмене или переносу: его увидит вторая сторона. */
export default function CommentField({ value, onChange, placeholder, footer }: Props) {
  const id = useId()
  return (
    <section className="section">
      <label className="section-title" htmlFor={id}>
        Комментарий
      </label>
      <div className="group">
        <textarea
          id={id}
          className="field-input"
          placeholder={placeholder}
          maxLength={MAX_COMMENT}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      </div>
      {footer && <p className="section-footer">{footer}</p>}
    </section>
  )
}
