import { undoLast, UNDO_MS, useToast } from '../undo'
import { haptic } from '../telegram'

/** Плашка внизу: «Заметка удалена · Отменить» с полоской оставшегося времени. */
export default function UndoToast() {
  const toast = useToast()
  if (!toast) return null
  return (
    <div className="undo-toast" role="status" key={toast.id}>
      <span>{toast.text}</span>
      {toast.undoable && (
        <>
          <button
            type="button"
            onClick={() => {
              haptic.tap()
              undoLast()
            }}
          >
            Отменить
          </button>
          <i className="undo-bar" style={{ animationDuration: `${UNDO_MS}ms` }} />
        </>
      )}
    </div>
  )
}
