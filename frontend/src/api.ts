// В проде Mini App и API живут на одном домене, поэтому по умолчанию адрес пустой
const API_URL = import.meta.env.VITE_API_URL ?? ''

export type Trainer = {
  id: number
  display_name: string
  timezone: string
  address: string | null
  auto_confirm: boolean
  cancel_hours: number
  // Шаг времени начала записи в минутах; 0 — равен длительности услуги
  slot_step_min: number
  // Правила занятий: клиенты подтверждают их перед записью; null — правил нет
  rules: string | null
  rules_updated_at: string | null
  // null: тренер ещё не прошёл первую настройку
  onboarded_at: string | null
}

export type Me = {
  id: number
  first_name: string
  last_name: string | null
  username: string | null
  is_trainer: boolean
  is_admin: boolean
  // Есть хотя бы один тренер, к которому можно записаться
  is_client: boolean
  trainer: Trainer | null
}

export type TrainerProfileInput = Partial<
  Pick<
    Trainer,
    | 'display_name'
    | 'timezone'
    | 'address'
    | 'auto_confirm'
    | 'cancel_hours'
    | 'slot_step_min'
    | 'rules'
  >
>

export type Service = {
  id: number
  name: string
  duration_min: number
  capacity: number
  price: number | null
  address: string | null
  is_active: boolean
}

export type ServiceInput = {
  name: string
  duration_min: number
  capacity: number
  price: number | null
  address: string | null
}

// Время приходит как "10:00:00"
export type Rule = {
  id: number
  weekday: number
  start: string
  end: string
  service_ids: number[]
}

export type RuleInput = Omit<Rule, 'id'>

// Промежуток рабочего времени; пустой service_ids — все услуги
export type Window = {
  start: string
  end: string
  service_ids: number[]
}

export type DayHours = {
  day: string
  // true — на дату заданы свои часы, false — работает шаблон недели
  custom: boolean
  // Пустой список — выходной
  windows: Window[]
}

export type Slot = {
  service_id: number
  starts_at: string
  ends_at: string
  // Сколько ещё человек можно записать; у индивидуальной услуги всегда 1
  seats_left: number
}

// Тренер, каким его видит клиент
export type ClientTrainer = {
  id: number
  display_name: string
  timezone: string
  address: string | null
  auto_confirm: boolean
  cancel_hours: number
  rules: string | null
  // Правила нужно прочитать и принять, прежде чем записываться
  rules_pending: boolean
}

export type BookingStatus = 'pending' | 'confirmed' | 'declined' | 'cancelled'

export type Person = {
  id: number
  first_name: string
  last_name: string | null
  username: string | null
}

export type Booking = {
  id: number
  status: BookingStatus
  starts_at: string
  ends_at: string
  created_by: 'client' | 'trainer'
  cancelled_by: 'client' | 'trainer' | null
  service: { id: number; name: string; duration_min: number; capacity: number }
  trainer: { id: number; display_name: string; timezone: string }
  client: Person
  // Адрес услуги или, если его нет, адрес тренера
  address: string | null
  // Может ли тот, кто смотрит, отменить запись прямо сейчас
  can_cancel: boolean
  // До какого момента клиент отменяет сам
  cancel_deadline: string
  // Отметка тренера после занятия; null — не отмечено
  attendance: Attendance | null
  // Можно ли уже отметить посещение: занятие началось и не отклонено
  can_mark: boolean
  // Разовая: списать не из чего, оплачивается отдельно. Для неотмеченных — прогноз
  one_off: boolean
  // Разовая у клиента, который покупал блоки: блок закончился, стоит продать новый
  out_of_block: boolean
  // Из какого блока списано занятие
  charge: BookingCharge | null
  // Неотмеченная запись: из какого блока спишется, если пройдёт
  planned: BookingCharge | null
}

export type BookingCharge = {
  package_id: number
  package_name: string
  // Какое по счёту занятие блока
  number: number
  sessions_count: number
}

// attended — прошла, missed_charged — пропуск со списанием, missed_free — без списания
export type Attendance = 'attended' | 'missed_charged' | 'missed_free'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

let accessToken: string | null = null

// FastAPI кладёт текст ошибки в detail: строкой или списком ошибок валидации
function errorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const { detail } = body as { detail: unknown }
    if (typeof detail === 'string') {
      return detail
    }
    if (Array.isArray(detail)) {
      return 'Проверьте заполнение полей'
    }
  }
  return fallback
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`)
  }
  const response = await fetch(`${API_URL}${path}`, { ...init, headers })
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null)
    throw new ApiError(
      response.status,
      errorMessage(body, `${response.status} ${response.statusText}`),
    )
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  return request<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) })
}

export async function loginWithTelegram(initData: string): Promise<void> {
  const { access_token } = await send<{ access_token: string }>('POST', '/api/auth/telegram', {
    init_data: initData,
  })
  accessToken = access_token
}

export function fetchMe(): Promise<Me> {
  return request<Me>('/api/me')
}

// Напоминания о занятиях: о своих записях (client) и о занятиях, которые проводишь (trainer)
export type ReminderRole = 'client' | 'trainer'

export type ReminderPrefs = {
  enabled: boolean
  // За сколько минут до начала напомнить
  offsets: number[]
  // Только у тренера: после занятия бот просит его отметить
  attendance_prompt: boolean
}

export type Reminders = {
  client: ReminderPrefs
  // null — не тренер
  trainer: ReminderPrefs | null
}

export function fetchReminders(): Promise<Reminders> {
  return request<Reminders>('/api/me/reminders')
}

export function saveReminders(role: ReminderRole, prefs: ReminderPrefs): Promise<ReminderPrefs> {
  return send<ReminderPrefs>('PUT', `/api/me/reminders/${role}`, prefs)
}

export function updateTrainer(changes: TrainerProfileInput): Promise<Trainer> {
  return send<Trainer>('PATCH', '/api/trainer/me', changes)
}

export function fetchServices(includeInactive = false): Promise<Service[]> {
  return request<Service[]>(`/api/trainer/services?include_inactive=${includeInactive}`)
}

export function createService(service: ServiceInput): Promise<Service> {
  return send<Service>('POST', '/api/trainer/services', service)
}

export function updateService(
  id: number,
  changes: Partial<ServiceInput> & { is_active?: boolean },
): Promise<Service> {
  return send<Service>('PATCH', `/api/trainer/services/${id}`, changes)
}

export function fetchRules(): Promise<Rule[]> {
  return request<Rule[]>('/api/trainer/schedule/rules')
}

export function createRule(rule: RuleInput): Promise<Rule> {
  return send<Rule>('POST', '/api/trainer/schedule/rules', rule)
}

export function replaceRule(id: number, rule: RuleInput): Promise<Rule> {
  return send<Rule>('PUT', `/api/trainer/schedule/rules/${id}`, rule)
}

export function deleteRule(id: number): Promise<void> {
  return send<void>('DELETE', `/api/trainer/schedule/rules/${id}`)
}

export function fetchDayHours(from: string, days: number): Promise<DayHours[]> {
  return request<DayHours[]>(`/api/trainer/schedule/days?from=${from}&days=${days}`)
}

// Одинаковые часы на несколько дат; пустой windows — выходной
export function setDays(days: string[], windows: Window[]): Promise<void> {
  return send<void>('PUT', '/api/trainer/schedule/days', { days, windows })
}

// Вернуть даты к шаблону недели
export function resetDays(days: string[]): Promise<void> {
  return send<void>('POST', '/api/trainer/schedule/days/reset', { days })
}

// Повторить неделю, в которую попадает day, на weeks следующих недель
export function copyWeek(day: string, weeks: number): Promise<void> {
  return send<void>('POST', '/api/trainer/schedule/days/copy-week', { day, weeks })
}

export function fetchSlots(days = 14, from?: string): Promise<Slot[]> {
  const start = from ? `&from=${from}` : ''
  return request<Slot[]>(`/api/trainer/slots?days=${days}${start}`)
}

// --- Клиент ---

export function fetchMyTrainers(): Promise<ClientTrainer[]> {
  return request<ClientTrainer[]>('/api/client/trainers')
}

export function acceptTrainerRules(trainerId: number): Promise<ClientTrainer> {
  return send<ClientTrainer>('POST', `/api/client/trainers/${trainerId}/rules/accept`)
}

export function fetchTrainerServices(trainerId: number): Promise<Service[]> {
  return request<Service[]>(`/api/client/trainers/${trainerId}/services`)
}

export function fetchTrainerSlots(
  trainerId: number,
  serviceId: number,
  days = 14,
  from?: string,
): Promise<Slot[]> {
  const start = from ? `&from=${from}` : ''
  return request<Slot[]>(
    `/api/client/trainers/${trainerId}/slots?service_id=${serviceId}&days=${days}${start}`,
  )
}

export function fetchMyBookings(): Promise<Booking[]> {
  return request<Booking[]>('/api/client/bookings')
}

// Все свои записи у тренера за период, включая прошедшие: для календаря
export function fetchMyBookingsFor(
  trainerId: number,
  from: string,
  days: number,
): Promise<Booking[]> {
  return request<Booking[]>(
    `/api/client/bookings?trainer_id=${trainerId}&from=${from}&days=${days}`,
  )
}

export function createMyBooking(booking: {
  trainer_id: number
  service_id: number
  starts_at: string
}): Promise<Booking> {
  return send<Booking>('POST', '/api/client/bookings', booking)
}

export function cancelMyBooking(id: number): Promise<Booking> {
  return send<Booking>('POST', `/api/client/bookings/${id}/cancel`)
}

// --- Записи и клиенты тренера ---

export type Client = Person & {
  // Когда клиент впервые открыл ссылку тренера
  since: string
  // Сколько занятий осталось в действующих блоках; null — действующих блоков нет
  sessions_left: number | null
  // Сколько клиент должен доплатить по блокам
  debt: number
  // Покупал ли клиент блоки вообще
  has_packages: boolean
  // Сколько будущих записей не покрыто блоками: они будут разовыми
  upcoming_one_off: number
}

export function fetchTrainerBookings(days = 14, from?: string): Promise<Booking[]> {
  const start = from ? `&from=${from}` : ''
  return request<Booking[]>(`/api/trainer/bookings?days=${days}${start}`)
}

export function fetchTrainerBooking(id: number): Promise<Booking> {
  return request<Booking>(`/api/trainer/bookings/${id}`)
}

export function fetchPendingBookings(): Promise<Booking[]> {
  return request<Booking[]>('/api/trainer/bookings/pending')
}

export function createTrainerBooking(booking: {
  client_id: number
  service_id: number
  starts_at: string
}): Promise<Booking> {
  return send<Booking>('POST', '/api/trainer/bookings', booking)
}

export type BookingAction = 'confirm' | 'decline' | 'cancel'

export function changeTrainerBooking(id: number, action: BookingAction): Promise<Booking> {
  return send<Booking>('POST', `/api/trainer/bookings/${id}/${action}`)
}

export function fetchClients(): Promise<Client[]> {
  return request<Client[]>('/api/trainer/clients')
}

export function fetchInviteLink(): Promise<string> {
  return request<{ url: string }>('/api/trainer/invite-link').then(({ url }) => url)
}

export function fetchUnmarkedBookings(): Promise<Booking[]> {
  return request<Booking[]>('/api/trainer/bookings/unmarked')
}

export function markAttendance(id: number, attendance: Attendance | null): Promise<Booking> {
  return send<Booking>('POST', `/api/trainer/bookings/${id}/attendance`, { attendance })
}

// --- Блоки ---

export type ServiceRef = { id: number; name: string }

export type PackageTemplate = {
  id: number
  name: string
  // null — подходит к любой услуге
  service: ServiceRef | null
  sessions_count: number
  price: number
  // Сколько дней действует с даты покупки; null — бессрочно
  valid_days: number | null
}

export type PackageTemplateInput = {
  name: string
  service_id: number | null
  sessions_count: number
  price: number
  valid_days: number | null
}

export type PackageStatus = 'active' | 'finished' | 'expired' | 'closed'

export type Payment = {
  id: number
  amount: number
  paid_on: string
  comment: string | null
}

export type PackageSession = {
  id: number
  // Порядковый номер в блоке, 1…N
  number: number
  day: string
  status: 'attended' | 'missed_charged'
  // null — отмечено в блоке вручную, без записи
  booking_id: number | null
}

export type Package = {
  id: number
  name: string
  trainer: { id: number; display_name: string; timezone: string }
  service: ServiceRef | null
  sessions_count: number
  price: number
  purchased_on: string
  valid_until: string | null
  closed_at: string | null
  status: PackageStatus
  used: number
  left: number
  paid: number
  // Сколько осталось доплатить
  due: number
  // Осталось 1–2 занятия: пора предложить новый блок
  ending_soon: boolean
  payments: Payment[]
  sessions: PackageSession[]
  // Неотмеченные записи, которые по прогнозу лягут в блок, по времени
  planned: PlannedSession[]
}

export type PlannedSession = {
  booking_id: number
  starts_at: string
  // Каким по счёту занятием блока станет
  number: number
}

export type PackageInput = {
  name: string
  service_id: number | null
  sessions_count: number
  price: number
  purchased_on: string
  valid_until: string | null
}

export type ClientCard = {
  client: Client
  notes: string | null
  // Новые первыми
  packages: Package[]
  // Все записи у тренера, новые первыми
  history: Booking[]
}

export function fetchPackageTemplates(): Promise<PackageTemplate[]> {
  return request<PackageTemplate[]>('/api/trainer/package-templates')
}

export function createPackageTemplate(template: PackageTemplateInput): Promise<PackageTemplate> {
  return send<PackageTemplate>('POST', '/api/trainer/package-templates', template)
}

export function replacePackageTemplate(
  id: number,
  template: PackageTemplateInput,
): Promise<PackageTemplate> {
  return send<PackageTemplate>('PUT', `/api/trainer/package-templates/${id}`, template)
}

export function deletePackageTemplate(id: number): Promise<void> {
  return send<void>('DELETE', `/api/trainer/package-templates/${id}`)
}

export function fetchClientCard(clientId: number): Promise<ClientCard> {
  return request<ClientCard>(`/api/trainer/clients/${clientId}`)
}

export function saveClientNotes(clientId: number, notes: string | null): Promise<void> {
  return send<void>('PUT', `/api/trainer/clients/${clientId}/notes`, { notes })
}

export function createPackage(clientId: number, data: PackageInput): Promise<Package> {
  return send<Package>('POST', `/api/trainer/clients/${clientId}/packages`, data)
}

export function updatePackage(
  id: number,
  changes: Partial<Omit<PackageInput, 'service_id'>> & { closed?: boolean },
): Promise<Package> {
  return send<Package>('PATCH', `/api/trainer/packages/${id}`, changes)
}

export function deletePackage(id: number): Promise<void> {
  return send<void>('DELETE', `/api/trainer/packages/${id}`)
}

export function addPayment(
  packageId: number,
  payment: { amount: number; paid_on: string; comment: string | null },
): Promise<Package> {
  return send<Package>('POST', `/api/trainer/packages/${packageId}/payments`, payment)
}

export function deletePayment(packageId: number, paymentId: number): Promise<Package> {
  return send<Package>('DELETE', `/api/trainer/packages/${packageId}/payments/${paymentId}`)
}

export function addManualSession(
  packageId: number,
  session: { day: string; attendance: 'attended' | 'missed_charged' },
): Promise<Package> {
  return send<Package>('POST', `/api/trainer/packages/${packageId}/sessions`, session)
}

export function updateManualSession(
  packageId: number,
  sessionId: number,
  session: { day: string; attendance: 'attended' | 'missed_charged' },
): Promise<Package> {
  return send<Package>('PATCH', `/api/trainer/packages/${packageId}/sessions/${sessionId}`, session)
}

export function deleteManualSession(packageId: number, sessionId: number): Promise<Package> {
  return send<Package>('DELETE', `/api/trainer/packages/${packageId}/sessions/${sessionId}`)
}

export function fetchMyPackages(): Promise<Package[]> {
  return request<Package[]>('/api/client/packages')
}
