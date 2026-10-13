import type { BookingStatus } from '../api'
import { BOOKING_STATUS } from '../format'

/** Статус записи цветной плашкой: ждёт — оранжевая, подтверждена — зелёная. */
export default function StatusBadge({ status }: { status: BookingStatus }) {
  return <span className={`badge ${status}`}>{BOOKING_STATUS[status]}</span>
}
