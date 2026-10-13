# Источник

Скилл скопирован из https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
(коммит 7246805992a42b7bba37d4cac83b01416f0c6c44, папка `.claude/skills/brand`), лицензия MIT — см. `LICENSE`.

Изменения относительно оригинала:
- удалена папка `scripts/tests` (тесты самого скилла).

Что учесть в Trenio:
- источник правды бренда — `docs/brand-guidelines.md`;
- `scripts/sync-brand-to-tokens.cjs` в Trenio не нужен: токены живут в `frontend/src/index.css`
  (скрипт сам остановится, увидев `:root`), а генератор CSS из соседнего скилла `design-system` мы не копировали.

Обновление: заново скопировать `.claude/skills/brand/` из нужного коммита апстрима
и повторить изменения выше.
