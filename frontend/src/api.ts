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

// telegram — фото из Telegram, custom — загружено своё, none — убрано
export type AvatarMode = 'telegram' | 'custom' | 'none'

export type Me = {
  id: number
  first_name: string
  last_name: string | null
  username: string | null
  // true — имя задано в профиле, а не взято из Telegram
  name_custom: boolean
  // Адрес фото; null — фото нет, показываем инициалы
  avatar_url: string | null
  avatar_mode: AvatarMode
  is_trainer: boolean
  is_admin: boolean
  // Есть хотя бы один тренер, к которому можно записаться
  is_client: boolean
  trainer: Trainer | null
  // Вводный тур пройден или пропущен; false — показать при входе в этот профиль
  trainer_tour_done: boolean
  client_tour_done: boolean
  // Нужно согласие с политикой обработки данных: впервые или после её изменения
  consent_required: boolean
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
  avatar_url: string | null
  // Телефон клиента, который записал этот тренер; клиент может его удалить
  my_phone: string | null
}

export type BookingStatus = 'pending' | 'confirmed' | 'declined' | 'cancelled'

export type Person = {
  id: number
  first_name: string
  last_name: string | null
  username: string | null
  // Адрес фото; null — фото нет, показываем инициалы
  avatar_url: string | null
}

export type Booking = {
  id: number
  status: BookingStatus
  starts_at: string
  ends_at: string
  created_by: 'client' | 'trainer'
  cancelled_by: 'client' | 'trainer' | null
  // Комментарий того, кто отменил или отклонил
  cancel_comment: string | null
  // Последний перенос: прежнее время, кто перенёс и комментарий
  rescheduled_from: string | null
  rescheduled_by: 'client' | 'trainer' | null
  reschedule_comment: string | null
  service: { id: number; name: string; duration_min: number; capacity: number }
  trainer: { id: number; display_name: string; timezone: string; avatar_url: string | null }
  client: Person
  // Адрес услуги или, если его нет, адрес тренера
  address: string | null
  // Может ли тот, кто смотрит, отменить или перенести запись прямо сейчас
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
  // Только тренеру: цена занятия, если оно разовое; null — цены нет
  price: number | null
  // Только тренеру: тренер решил не списывать занятие из блока
  no_package: boolean
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

export type MyName = { first_name: string; last_name: string | null; name_custom: boolean }

// Своё имя, которое видит тренер; Telegram его больше не перезаписывает
export function saveMyName(firstName: string, lastName: string | null): Promise<MyName> {
  return send<MyName>('PUT', '/api/me/name', { first_name: firstName, last_name: lastName })
}

export function resetMyName(): Promise<MyName> {
  return send<MyName>('DELETE', '/api/me/name')
}

// --- Персональные данные ---

export type Policy = { version: number; text: string }

export function fetchPolicy(): Promise<Policy> {
  return request<Policy>('/api/privacy')
}

export function giveConsent(): Promise<void> {
  return send<void>('POST', '/api/me/consent')
}

// Удалить аккаунт: записи и оплаты у тренеров останутся обезличенными
export function deleteAccount(): Promise<void> {
  return send<void>('DELETE', '/api/me')
}

// Телефон клиента; null — удалить. consent — клиент согласен его хранить
export function saveClientPhone(
  clientId: number,
  phone: string | null,
  consent: boolean,
): Promise<{ phone: string | null }> {
  return send('PUT', `/api/trainer/clients/${clientId}/phone`, { phone, consent })
}

export function removeMyPhone(trainerId: number): Promise<void> {
  return send<void>('DELETE', `/api/client/trainers/${trainerId}/phone`)
}

export type TourRole = 'trainer' | 'client'

// Тур пройден или пропущен: сам больше не покажется, только из Профиля
export function finishTour(role: TourRole): Promise<void> {
  return send<void>('POST', `/api/me/tour/${role}`)
}

export type AvatarState = { avatar_url: string | null; avatar_mode: AvatarMode }

// Своё фото: JPEG, уже обрезанный и сжатый в Mini App
export async function uploadAvatar(photo: Blob): Promise<AvatarState> {
  const response = await fetch(`${API_URL}/api/me/avatar`, {
    method: 'PUT',
    headers: { 'Content-Type': 'image/jpeg', Authorization: `Bearer ${accessToken ?? ''}` },
    body: photo,
  })
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null)
    throw new ApiError(response.status, errorMessage(body, 'Не удалось загрузить фото'))
  }
  return (await response.json()) as AvatarState
}

export function removeAvatar(): Promise<AvatarState> {
  return send<AvatarState>('DELETE', '/api/me/avatar')
}

export function restoreTelegramAvatar(): Promise<AvatarState> {
  return send<AvatarState>('POST', '/api/me/avatar/telegram')
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

// serviceId — только окошки этой услуги; reschedule — переносимая запись, её время тоже свободно
export function fetchSlots(
  days = 14,
  from?: string,
  serviceId?: number,
  reschedule?: number,
): Promise<Slot[]> {
  const params = new URLSearchParams({ days: String(days) })
  if (from) params.set('from', from)
  if (serviceId !== undefined) params.set('service_id', String(serviceId))
  if (reschedule !== undefined) params.set('reschedule', String(reschedule))
  return request<Slot[]>(`/api/trainer/slots?${params}`)
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
  reschedule?: number,
): Promise<Slot[]> {
  const params = new URLSearchParams({ service_id: String(serviceId), days: String(days) })
  if (from) params.set('from', from)
  if (reschedule !== undefined) params.set('reschedule', String(reschedule))
  return request<Slot[]>(`/api/client/trainers/${trainerId}/slots?${params}`)
}

export function fetchMyBookings(): Promise<Booking[]> {
  return request<Booking[]>('/api/client/bookings')
}

// Прошедшие, отменённые и отклонённые записи, новые сверху; before — id последней загруженной
export function fetchMyHistory(before?: number): Promise<Booking[]> {
  return request<Booking[]>(`/api/client/bookings/history${before ? `?before=${before}` : ''}`)
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

export function cancelMyBooking(id: number, comment?: string): Promise<Booking> {
  return send<Booking>('POST', `/api/client/bookings/${id}/cancel`, { comment: comment || null })
}

export function rescheduleMyBooking(
  id: number,
  startsAt: string,
  comment?: string,
): Promise<Booking> {
  return send<Booking>('POST', `/api/client/bookings/${id}/reschedule`, {
    starts_at: startsAt,
    comment: comment || null,
  })
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
  // Клиент без Telegram, которого тренер завёл сам: имя правит тренер, уведомлений нет
  offline: boolean
  // Клиент удалил аккаунт: осталась обезличенная история, записать его нельзя
  deleted: boolean
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

// Свои условия одного занятия; не переданное — как у услуги или как было
export type BookingTermsInput = {
  duration_min?: number
  price?: number
  no_package?: boolean
}

export function createTrainerBooking(
  booking: { client_id: number; service_id: number; starts_at: string } & BookingTermsInput,
): Promise<Booking> {
  return send<Booking>('POST', '/api/trainer/bookings', booking)
}

export function setBookingTerms(bookingId: number, terms: BookingTermsInput): Promise<Booking> {
  return send<Booking>('PATCH', `/api/trainer/bookings/${bookingId}/terms`, terms)
}

export type BookingAction = 'confirm' | 'decline' | 'cancel'

// comment — для отмены и отклонения, необязательный
export function changeTrainerBooking(
  id: number,
  action: BookingAction,
  comment?: string,
): Promise<Booking> {
  return send<Booking>('POST', `/api/trainer/bookings/${id}/${action}`, {
    comment: comment || null,
  })
}

export function rescheduleTrainerBooking(
  id: number,
  startsAt: string,
  comment?: string,
): Promise<Booking> {
  return send<Booking>('POST', `/api/trainer/bookings/${id}/reschedule`, {
    starts_at: startsAt,
    comment: comment || null,
  })
}

export function fetchClients(): Promise<Client[]> {
  return request<Client[]>('/api/trainer/clients')
}

export function fetchInviteLink(): Promise<string> {
  return request<{ url: string }>('/api/trainer/invite-link').then(({ url }) => url)
}

export type ClientName = {
  first_name: string
  last_name: string | null
}

export function createClient(data: ClientName & { notes: string | null }): Promise<Client> {
  return send<Client>('POST', '/api/trainer/clients', data)
}

export function renameClient(clientId: number, data: ClientName): Promise<Client> {
  return send<Client>('PATCH', `/api/trainer/clients/${clientId}`, data)
}

/** Личная ссылка клиента без Telegram: открыв её, он привяжет свой аккаунт. */
export function fetchClaimLink(clientId: number): Promise<string> {
  return send<{ url: string }>('POST', `/api/trainer/clients/${clientId}/claim-link`).then(
    ({ url }) => url,
  )
}

/** Клиент без Telegram и клиент из Telegram — один человек: история переезжает ко второму. */
export function mergeClient(clientId: number, intoId: number): Promise<void> {
  return send<void>('POST', `/api/trainer/clients/${clientId}/merge`, { into_id: intoId })
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
  // Телефон клиента: видит только этот тренер
  phone: string | null
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

// Адрес картинки с сервера: avatar_url приходит как путь /api/avatars/…
export function mediaUrl(path: string): string {
  return `${API_URL}${path}`
}

// --- Финансы тренера ---

export type MonthPoint = { month: string; received: number; worked: number }

export type FinanceSummary = {
  // "2026-10"
  month: string
  // Получено: оплаты блоков по датам и разовые занятия
  received: number
  received_prev: number
  incomes_count: number
  // Отработано: стоимость проведённых и списанных занятий
  worked: number
  worked_sessions: number
  clients: number
  // Сейчас: долги по блокам и деньги за ещё не отработанные занятия
  debt: number
  debt_clients: number
  advance: number
  // Оставшиеся в месяце записи и их стоимость
  planned: number
  planned_count: number
  from_packages: number
  from_one_off: number
  // Полгода, заканчивая этим месяцем
  chart: MonthPoint[]
}

export type FinanceYear = {
  year: number
  received: number
  worked: number
  worked_sessions: number
  months: MonthPoint[]
}

export type FinanceMonth = {
  month: string
  incomes: {
    day: string
    client: Person
    kind: 'payment' | 'one_off'
    label: string
    amount: number
  }[]
  clients: { client: Person; received: number; worked: number; sessions: number }[]
}

export type FinanceForecast = {
  days: number
  total: number
  one_off: number
  one_off_count: number
  dues: {
    client: Person
    package_id: number
    package_name: string
    price: number
    paid: number
    due: number
  }[]
  renewals: {
    client: Person
    package_id: number
    package_name: string
    sessions_count: number
    left: number
    price: number
  }[]
}

export function fetchFinanceSummary(month: string): Promise<FinanceSummary> {
  return request<FinanceSummary>(`/api/trainer/finance/summary?month=${month}`)
}

export function fetchFinanceYear(year: number): Promise<FinanceYear> {
  return request<FinanceYear>(`/api/trainer/finance/year?year=${year}`)
}

export function fetchFinanceMonth(month: string): Promise<FinanceMonth> {
  return request<FinanceMonth>(`/api/trainer/finance/month?month=${month}`)
}

export function fetchFinanceForecast(): Promise<FinanceForecast> {
  return request<FinanceForecast>('/api/trainer/finance/forecast')
}

// --- Админ-панель ---

export type AdminOverview = {
  users: number
  users_seen_week: number
  trainers: number
  trainers_active: number
  trainers_disabled: number
  clients: number
  clients_new_week: number
  bookings_week: number
  attended_week: number
  upcoming_week: number
  invites_open: number
  notifications_sent_day: number
  notifications_failed_day: number
  version: string
  // Понедельник недели и сколько пришло
  weeks: { start: string; new_clients: number; new_trainers: number }[]
  funnel: {
    trainers: number
    onboarded: number
    set_up: number
    with_clients: number
    with_bookings: number
  }
  // Деньги всей платформы за текущий месяц, без разбивки по тренерам
  money: {
    month: string
    received: number
    received_prev: number
    packages_sold: number
    packages_amount: number
  }
}

export type AdminTrainerState = 'active' | 'quiet' | 'not_set_up' | 'disabled'

export type AdminTrainer = {
  id: number
  display_name: string
  avatar_url: string | null
  user: Person
  state: AdminTrainerState
  is_admin: boolean
  since: string
  timezone: string
  clients: number
  clients_new_week: number
  bookings_month: number
  attended_month: number
  services: number
  last_booking_at: string | null
  last_seen_at: string | null
}

export function fetchAdminOverview(): Promise<AdminOverview> {
  return request<AdminOverview>('/api/admin/overview')
}

export function fetchAdminTrainers(): Promise<AdminTrainer[]> {
  return request<AdminTrainer[]>('/api/admin/trainers')
}

export function setTrainerActive(id: number, active: boolean): Promise<void> {
  return send<void>('POST', `/api/admin/trainers/${id}/active`, { active })
}

export function createTrainerInvite(): Promise<{ url: string; expires_at: string }> {
  return send<{ url: string; expires_at: string }>('POST', '/api/admin/invites')
}

export function fetchOpenInvites(): Promise<{ created_at: string; expires_at: string }[]> {
  return request<{ created_at: string; expires_at: string }[]>('/api/admin/invites')
}
