import { useState, type ReactNode } from 'react'
import { post, type AdminTrainer } from '../api'
import { errorText, plural, shortDate } from '../format'
import { Modal } from './common'

export type TrainerAction = 'pro' | 'message' | 'delete'

type Props = { trainer: AdminTrainer; onClose: () => void; onDone: (note: string) => void }

// Общая форма диалога: ошибка, «Отмена» и кнопка действия
function ActionForm({
  onSubmit,
  onClose,
  busy,
  error,
  submit,
  danger = false,
  disabled = false,
  children,
}: {
  onSubmit: () => void
  onClose: () => void
  busy: boolean
  error: string | null
  submit: string
  danger?: boolean
  disabled?: boolean
  children: ReactNode
}) {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit()
      }}
      style={{ display: 'flex', flexDirection: 'column', gap: 14 }}
    >
      {children}
      {error && (
        <p role="alert" className="small" style={{ margin: 0, color: 'var(--red)' }}>
          {error}
        </p>
      )}
      <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
        <button type="button" className="btn secondary" onClick={onClose} disabled={busy}>
          Отмена
        </button>
        <button type="submit" className={danger ? 'btn danger' : 'btn'} disabled={busy || disabled}>
          {busy ? 'Минуту…' : submit}
        </button>
      </div>
    </form>
  )
}

function useSubmit(onDone: (note: string) => void) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const run = async (action: () => Promise<string>) => {
    setBusy(true)
    setError(null)
    try {
      onDone(await action())
    } catch (reason) {
      setError(errorText(reason))
      setBusy(false)
    }
  }
  return { busy, error, run }
}

const PRO_DAYS = [7, 30, 90]

function ProDialog({ trainer, onClose, onDone }: Props) {
  const [days, setDays] = useState(30)
  const { busy, error, run } = useSubmit(onDone)
  const now = new Date()
  const ends = [trainer.pro_until, trainer.trial_until]
    .filter((value): value is string => value !== null && new Date(value) > now)
    .sort()
    .at(-1)
  return (
    <Modal title={`Pro в подарок: ${trainer.display_name}`} onClose={onClose}>
      <ActionForm
        busy={busy}
        error={error}
        onClose={onClose}
        submit={`Подарить ${days} дн.`}
        disabled={!(days >= 1 && days <= 366)}
        onSubmit={() =>
          run(async () => {
            const result = await post<{ pro_until: string }>(`/admin/trainers/${trainer.id}/pro`, { days })
            return `${trainer.display_name}: Pro до ${shortDate(result.pro_until)}`
          })
        }
      >
        <p className="small" style={{ margin: 0 }}>
          {ends ? `Сейчас доступ до ${shortDate(ends)}. Дни добавятся после этой даты.` : 'Сейчас бесплатный тариф. Pro начнётся сегодня.'}
        </p>
        <div className="chips" role="group" aria-label="Сколько дней">
          {PRO_DAYS.map((value) => (
            <button key={value} type="button" className="chip" aria-pressed={days === value} onClick={() => setDays(value)}>
              {value} дней
            </button>
          ))}
        </div>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span className="small">Или своё число дней</span>
          <input className="field" type="number" min={1} max={366} value={days} onChange={(event) => setDays(Number(event.target.value))} />
        </label>
      </ActionForm>
    </Modal>
  )
}

function MessageDialog({ trainer, onClose, onDone }: Props) {
  const [text, setText] = useState('')
  const { busy, error, run } = useSubmit(onDone)
  return (
    <Modal title={`Сообщение: ${trainer.display_name}`} onClose={onClose}>
      <ActionForm
        busy={busy}
        error={error}
        onClose={onClose}
        submit="Отправить в бот"
        disabled={!text.trim()}
        onSubmit={() =>
          run(async () => {
            await post(`/admin/trainers/${trainer.id}/message`, { text })
            return `Сообщение для ${trainer.display_name} отправлено`
          })
        }
      >
        <p className="small muted" style={{ margin: 0 }}>
          Придёт от бота с подписью «Сообщение от команды Trenio». Ответ тренер пришлёт вам в личку
          {trainer.user.username ? '' : ': у него нет @username, так что дайте свой контакт в тексте'}.
        </p>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span className="sr">Текст сообщения</span>
          <textarea
            className="field"
            rows={6}
            maxLength={3500}
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="Привет! Видим, что вы ещё не настроили расписание. Помочь?"
            autoFocus
            style={{ padding: 12, resize: 'vertical' }}
          />
        </label>
      </ActionForm>
    </Modal>
  )
}

function DeleteDialog({ trainer, onClose, onDone }: Props) {
  const [name, setName] = useState('')
  const [reason, setReason] = useState('')
  const { busy, error, run } = useSubmit(onDone)
  const matches = name.trim().toLowerCase() === trainer.display_name.trim().toLowerCase()
  return (
    <Modal title={`Удалить тренера ${trainer.display_name}?`} onClose={onClose}>
      <ActionForm
        busy={busy}
        error={error}
        onClose={onClose}
        submit="Удалить навсегда"
        danger
        disabled={!matches || !reason.trim()}
        onSubmit={() =>
          run(async () => {
            await post(`/admin/trainers/${trainer.id}/delete`, { confirm_name: name, reason })
            return `${trainer.display_name} удалён`
          })
        }
      >
        <p className="small" style={{ margin: 0 }}>
          Отменить это нельзя. Удалятся услуги, расписание, записи, блоки и клиенты без Telegram ({trainer.clients}{' '}
          {plural(trainer.clients, 'клиент', 'клиента', 'клиентов')} всего). Клиенты с Telegram останутся, но потеряют этого тренера. Если нужно
          просто закрыть доступ, лучше «Отключить»: данные сохранятся.
        </p>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span className="small">
            Наберите имя тренера: <b>{trainer.display_name}</b>
          </span>
          <input className="field" value={name} onChange={(event) => setName(event.target.value)} autoFocus />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span className="small">Причина</span>
          <input className="field" maxLength={500} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Например: попросил сам" />
          <span className="tiny muted">Попадёт в журнал действий.</span>
        </label>
      </ActionForm>
    </Modal>
  )
}

export function TrainerActionDialog({ action, ...props }: Props & { action: TrainerAction }) {
  if (action === 'pro') return <ProDialog {...props} />
  if (action === 'message') return <MessageDialog {...props} />
  return <DeleteDialog {...props} />
}
