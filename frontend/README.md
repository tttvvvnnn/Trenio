# Trenio Mini App

React + TypeScript + Vite. Открывается из Telegram кнопкой в боте.

```bash
npm ci
npm run dev     # http://localhost:5173, запросы /api уходят на backend :8000
npm run lint
npm run build   # статика в dist/, её раздаёт nginx
```

Вне Telegram приложение покажет подсказку «Откройте Trenio из Telegram»:
войти можно только с подписанной initData.
