#!/bin/bash
# После правки .py в backend: ruff check --fix и ruff format, как проверяет CI.
# Если ошибки остались, отдаёт их Claude (код 2)
set -uo pipefail

file=$(python3 -c 'import json, sys; print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))')
case "$file" in
  "$CLAUDE_PROJECT_DIR"/backend/*.py) ;;
  *) exit 0 ;;
esac
[ -f "$file" ] || exit 0

ruff="$CLAUDE_PROJECT_DIR/backend/.venv/bin/ruff"
[ -x "$ruff" ] || ruff=$(command -v ruff) || exit 0

cd "$CLAUDE_PROJECT_DIR/backend"
"$ruff" format --quiet "$file"
if ! out=$("$ruff" check --fix --quiet "$file" 2>&1); then
  echo "ruff check нашёл ошибки в $file:" >&2
  echo "$out" >&2
  exit 2
fi
