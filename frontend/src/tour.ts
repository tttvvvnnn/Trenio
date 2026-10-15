import type { TourStep } from './ui/Tour'

/*
 * Шаги вводного тура. Подсвечиваем в основном вкладки: они есть всегда,
 * даже у нового тренера без клиентов и окошек.
 */

export type TrainerTab = 'calendar' | 'clients' | 'schedule' | 'finance' | 'profile'
export type ClientTab = 'book' | 'bookings' | 'packages' | 'profile'

// Строка «Как пользоваться» в Профиле, последний шаг обоих туров
export const TOUR_REPLAY = 'tour-replay'

export const TRAINER_TOUR: readonly TourStep<TrainerTab>[] = [
  {
    tab: 'calendar',
    title: 'Добро пожаловать в Trenio',
    text: 'Клиенты записываются к вам сами, без переписки. Покажу главное, это займёт минуту.',
  },
  {
    tab: 'schedule',
    target: 'tab-schedule',
    title: 'Начните с расписания',
    text: 'Задайте рабочую неделю и исключения. Из этих часов получаются окошки, в которые записываются клиенты.',
  },
  {
    tab: 'profile',
    target: 'services',
    title: 'Услуги и блоки',
    text: 'Добавьте, что вы проводите: длительность и цену. Здесь же шаблоны блоков занятий, а ниже правила для клиентов.',
  },
  {
    tab: 'clients',
    target: 'invite-link',
    title: 'Пригласите клиентов',
    text: 'Здесь ваша ссылка для клиентов. Клиент откроет её в Telegram и сможет сам выбирать время.',
  },
  {
    tab: 'calendar',
    target: 'tab-calendar',
    title: 'Записи',
    text: 'Ближайшие занятия и заявки, которые ждут подтверждения. После занятия отметьте, пришёл ли клиент: так занятие списывается из блока.',
  },
  {
    tab: 'finance',
    target: 'tab-finance',
    title: 'Финансы',
    text: 'Доход по оплатам, которые вы отмечаете, и прогноз на месяц.',
  },
  {
    tab: 'profile',
    target: TOUR_REPLAY,
    title: 'Вот и всё',
    text: 'Тур можно пройти снова в любой момент: он здесь, в Профиле.',
  },
]

export const CLIENT_TOUR: readonly TourStep<ClientTab>[] = [
  {
    tab: 'book',
    title: 'Добро пожаловать в Trenio',
    text: 'Здесь вы сами записываетесь к тренеру, без переписки. Покажу, где что.',
  },
  {
    tab: 'book',
    target: 'tab-book',
    title: 'Запись',
    text: 'Выберите день и свободное время. Если тренер подтверждает записи сам, придёт уведомление.',
  },
  {
    tab: 'bookings',
    target: 'tab-bookings',
    title: 'Мои записи',
    text: 'Ближайшие занятия: их можно перенести или отменить. Прошедшие на вкладке «История».',
  },
  {
    tab: 'packages',
    target: 'tab-packages',
    title: 'Блоки',
    text: 'Купленные блоки занятий: сколько оплачено и сколько занятий осталось.',
  },
  {
    tab: 'profile',
    target: TOUR_REPLAY,
    title: 'Профиль',
    text: 'Имя и фото для тренера, напоминания и правила занятий. Тур можно повторить здесь.',
  },
]
