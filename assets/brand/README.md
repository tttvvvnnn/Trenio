# Логотип Trenio

Правила использования описаны в [docs/brand-guidelines.md](../../docs/brand-guidelines.md).

| Файл | Что это | Где использовать |
|---|---|---|
| `trenio-mark.svg` | Знак-секундомер, графит и коралл | Светлый фон |
| `trenio-mark-white.svg` | Знак, белый и коралл | Тёмный фон |
| `trenio-mark-mono-dark.svg`, `trenio-mark-mono-light.svg` | Одноцветный знак, сектор прозрачный | Когда нельзя цвет |
| `trenio-wordmark.svg` | Слово trenio, секундомер вместо o | Светлый фон |
| `trenio-wordmark-white.svg` | Слово, белое | Тёмный фон |
| `trenio-wordmark-mono-dark.svg`, `trenio-wordmark-mono-light.svg` | Одноцветное слово | Когда нельзя цвет |
| `bot-avatar.svg`, `bot-avatar.png` | 640×640, цветной знак на светлом фоне | Аватарка бота в @BotFather |
| `bot-description.svg`, `bot-description.png` | 640×360, цветное слово на светлом фоне | Картинка в описании бота (@BotFather) |
| `app-icon.svg`, `app-icon.png` | 1024×1024, графитовый фон | Иконка приложения, сторы |

В `frontend/public/` лежат `favicon.svg` (в тёмной теме браузера корпус белый)
и `apple-touch-icon.png` (180×180).

## Как пересобрать

Все SVG собирает `build.py`, слово набрано шрифтом Rubik ExtraBold и переведено в кривые,
поэтому шрифт для отображения не нужен.

```bash
python3 -m pip install fonttools
# Rubik[wght].ttf: https://fonts.google.com/specimen/Rubik (лицензия OFL)
python3 assets/brand/build.py path/to/Rubik[wght].ttf
# PNG из SVG, нужен Playwright с Chromium
node assets/brand/render.cjs
```
