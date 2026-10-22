#!/bin/bash
# Не даёт Claude править файлы, которые ведутся не руками:
# секреты, lock-файлы, версии и CHANGELOG (release-please), уже выпущенные миграции
set -uo pipefail

file=$(python3 -c 'import json, sys; print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))')
[ -n "$file" ] || exit 0
rel=${file#"$CLAUDE_PROJECT_DIR"/}

block() {
  echo "Нельзя править $rel: $1" >&2
  exit 2
}

case "$(basename "$rel")" in
  .env | .env.*)
    [ "$(basename "$rel")" = .env.example ] || block "секреты, меняются только на сервере" ;;
  uv.lock | package-lock.json)
    block "lock-файл обновляется командой uv lock или npm install" ;;
  CHANGELOG.md | .release-please-manifest.json)
    block "его ведёт release-please" ;;
esac

# Миграция, которая уже есть в main, могла примениться на dev и prod. Нужна новая миграция
case "$rel" in
  backend/src/trenio/migrations/versions/*.py)
    if git -C "$CLAUDE_PROJECT_DIR" cat-file -e "origin/main:$rel" 2>/dev/null; then
      block "миграция уже в main, создай новую через alembic revision"
    fi ;;
esac
exit 0
