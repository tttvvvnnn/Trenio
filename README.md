# Trenio

Telegram-бот и Mini App для фитнес-тренеров: тренер ведёт расписание и блоки тренировок, клиенты сами записываются в свободные окошки.

Проектный документ: https://claude.ai/code/artifact/77433b56-cf56-4d5e-8ecc-ecf48dce310a

## Структура

| Папка | Что внутри |
| --- | --- |
| `backend/` | Python: API (FastAPI), бот (aiogram), планировщик напоминаний |
| `frontend/` | Mini App (React + TypeScript + Vite) |

## Как устроен backend

Один пакет `trenio`, одна команда с разными ролями:

| Команда | Что запускает |
| --- | --- |
| `python -m trenio all` | API, бот и планировщик в одном процессе (компактная схема на сервере) |
| `python -m trenio api` | только HTTP API |
| `python -m trenio bot` | только бот |
| `python -m trenio scheduler` | только планировщик |
| `python -m trenio migrate` | применить миграции базы |

Все настройки приходят из переменных окружения, список в `.env.example`.
`GET /health` отвечает, жив ли сервис и доступна ли база.

## Разработка

Docker на ноутбуке не нужен: код проверяется в CI, а запускается на сервере.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy src tests && pytest
```

Тесты API и миграций идут, только если задан `TEST_DATABASE_URL`
(в CI его даёт контейнер PostgreSQL), иначе они пропускаются.

Новая миграция после изменения моделей:

```bash
alembic revision --autogenerate -m "что изменилось"
```

Mini App: см. `frontend/README.md`.
