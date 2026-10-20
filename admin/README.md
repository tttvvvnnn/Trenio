# Веб-админка Trenio

Отдельное приложение на поддомене `admin.<домен>`: React, TypeScript, Vite. Ходит только
в `/api` того же backend, что и Mini App.

## Вход

1. Telegram Login Widget на странице входа. Пускает только `ADMIN_TELEGRAM_IDS`.
2. В бот приходит «Вход в веб-админку … Это вы?». Пока не нажата «Да, это я», админка
   закрыта. Запрос живёт 10 минут.
3. После подтверждения backend держит вход в httpOnly-куке (`SameSite=Strict`, 12 часов).
   Изменяющие запросы несут `X-CSRF-Token`.

Входы и действия пишутся в `admin_audit_log`. Строки там только добавляются.

## Локально

```bash
npm install
npm run dev   # http://localhost:5174, /api проксируется на http://localhost:8000
```

Виджет Telegram работает только на домене, привязанном к боту (`/setdomain` в @BotFather),
поэтому локально вход через него не пройдёт.

## На сервере (один раз)

1. DNS: `admin.<домен>` на тот же сервер.
2. В `.env` окружения: `ADMIN_PORT=8082` для dev, `8083` для prod.
3. Edge nginx: поддомен проксирует на `127.0.0.1:$ADMIN_PORT`, сертификат через certbot.
4. @BotFather → бот окружения → `/setdomain` → `admin.<домен>`.
