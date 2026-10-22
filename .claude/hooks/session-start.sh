#!/bin/bash
# Готовит облачную сессию Claude Code: зависимости backend, frontend и admin
# и локальный PostgreSQL для тестов (как service-контейнер в CI)
set -euo pipefail

# Только в облачной сессии: на ноутбуке ничего не ставим
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

# Backend: venv в backend/.venv строго по uv.lock, вместе с dev-инструментами.
# --frozen и npm ci не переписывают lock-файлы
(cd backend && uv sync --frozen --extra dev --quiet)

# Mini App и веб-админка
(cd frontend && npm ci --no-audit --no-fund --silent)
(cd admin && npm ci --no-audit --no-fund --silent)

# PostgreSQL 16 с теми же пользователем и базой, что в CI
if ! pg_lsclusters --no-header | grep -q '^16 \+main \+5432 \+online'; then
  pg_ctlcluster 16 main start
fi
su postgres -c "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname = 'trenio'\"" | grep -q 1 \
  || su postgres -c "psql -qc \"CREATE ROLE trenio LOGIN PASSWORD 'trenio'\""
su postgres -c "psql -tAc \"SELECT 1 FROM pg_database WHERE datname = 'trenio_test'\"" | grep -q 1 \
  || su postgres -c "createdb -O trenio trenio_test"

if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  {
    echo "export PATH=\"$CLAUDE_PROJECT_DIR/backend/.venv/bin:\$PATH\""
    echo "export TEST_DATABASE_URL=postgresql+asyncpg://trenio:trenio@localhost:5432/trenio_test"
  } >> "$CLAUDE_ENV_FILE"
fi
