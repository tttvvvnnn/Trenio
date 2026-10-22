# Trenio

Telegram-бот и Mini App для персональных тренеров (@TrenioRuBot). Подробное описание
продукта и устройства в [README.md](README.md).

## Части репозитория

| Папка | Что это | Стек |
| --- | --- | --- |
| `backend/` | Пакет `trenio`: API, бот, планировщик, модели, миграции, тесты | Python 3.12, FastAPI, aiogram 3, SQLAlchemy 2 async, Alembic, APScheduler |
| `frontend/` | Mini App: экраны тренера, клиента и админа | React 19, TypeScript, Vite, @telegram-apps/sdk |
| `admin/` | Веб-админка на поддомене admin. | React 19, TypeScript, Vite |
| `deploy/` | Деплой, бэкап, проверка восстановления, systemd | bash |

Вся бизнес-логика живёт в `backend/src/trenio/services/`. Роуты API (`api/routes/`) и
хендлеры бота (`bot/`) только вызывают сервисы. Новую логику кладём в сервис, а не в роут.

## Проверки (как в CI)

Перед PR прогоняй проверки той части, которую менял. CI требует, чтобы все были зелёными.

```bash
# backend
cd backend
ruff check . && ruff format --check . && mypy src tests && pytest

# frontend и admin
cd frontend && npm run lint && npm run build
cd admin && npm run lint && npm run build
```

- mypy в режиме `strict`: у новых функций нужны аннотации типов.
- Тесты с базой идут, только если задан `TEST_DATABASE_URL`, иначе они пропускаются
  молча. В облачной сессии его выставляет хук `.claude/hooks/session-start.sh` и поднимает
  локальный PostgreSQL. Если тесты «прошли» подозрительно быстро, проверь, что они
  не пропущены (`pytest -rs`).
- Тесты для нового поведения пиши рядом с похожими в `backend/tests/`, фабрики
  в `tests/factories.py`. У frontend и admin тестов нет, только lint и build.

## Миграции

```bash
cd backend
alembic revision --autogenerate -m "что изменилось"
```

- Имена файлов: `YYYYMMDD_<revision>_<name>.py` в `src/trenio/migrations/versions/`.
- Миграцию, которая уже в `main`, не меняем: она могла примениться на dev и prod.
  Нужна правка схемы, значит новая миграция. Хук `protect-files.sh` это запрещает.
- `down_revision` новой миграции указывает на текущую последнюю.

## Коммиты, PR и релизы

- Коммиты и заголовки PR на русском в формате Conventional Commits:
  `feat: ...`, `fix(admin): ...`, `chore: ...`. От типа зависит раздел CHANGELOG.
- Версию (`pyproject.toml`, оба `package.json`), `CHANGELOG.md` и
  `.release-please-manifest.json` ведёт release-please. Руками их не правим.
- Мердж в `main` сам выкатывается на dev. На prod уходит только релизный PR release-please
  после подтверждения в окружении `deploy-prod`. Релизный PR мерджит владелец проекта.
- `uv.lock` и `package-lock.json` меняются только через `uv lock` и `npm install`.

## Настройки и секреты

Все настройки приходят из переменных окружения, список в [`.env.example`](.env.example).
Новую переменную добавляй в `.env.example` с комментарием. `.env` не читаем и не правим.

## Тексты и стиль

- Интерфейс, тексты бота, комментарии в коде и документация на русском.
- Фирменный стиль в [docs/brand-guidelines.md](docs/brand-guidelines.md). Для UI есть
  навыки `.claude/skills/ui-ux-pro-max` и `.claude/skills/brand`.

## Два бота на одной базе

Планируется второй, универсальный бот с нейтральным брендом на этой же кодовой базе и
этой же БД. Trenio при этом остаётся ботом только для тренеров. Поэтому:

- данные одного бота не должны быть видны в другом: запросы фильтруют по боту;
- всё, что зависит от бренда (название, логотип, тексты, цвета), держим в слое бренда,
  а не в общем ядре.
