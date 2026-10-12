#!/usr/bin/env bash
# Выкатка Trenio на сервер. Лежит в /opt/trenio/bin/deploy.sh (владелец root).
#
# GitHub Actions заходит по SSH ключом, у которого в authorized_keys стоит
#   command="/opt/trenio/bin/deploy.sh dev",restrict ssh-ed25519 ...
# Поэтому окружение задаёт сервер, а не GitHub. Тег образа приходит из
# SSH_ORIGINAL_COMMAND: GitHub выполняет `ssh deploy@host sha-<коммит>`.
#
# Вручную: sudo -u deploy /opt/trenio/bin/deploy.sh dev sha-<коммит>
#          sudo -u deploy /opt/trenio/bin/deploy.sh prod 0.2.0
set -euo pipefail

ENV_NAME="${1:-}"
TAG="${2:-${SSH_ORIGINAL_COMMAND:-}}"
REPO_RAW="https://raw.githubusercontent.com/tttvvvnnn/Trenio"
BACKUP_DIR="/opt/trenio/backups"
KEEP_BACKUPS=10

# Принимаем только известные окружения и теги строгого вида:
# в SSH_ORIGINAL_COMMAND может прийти что угодно
case "$ENV_NAME" in
  dev)
    PORT=8080
    [[ "$TAG" =~ ^sha-[0-9a-f]{40}$ ]] || { echo "dev ждёт тег sha-<40 hex>, пришло: '$TAG'" >&2; exit 2; }
    REF="${TAG#sha-}"
    ;;
  prod)
    PORT=8081
    [[ "$TAG" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "prod ждёт тег X.Y.Z, пришло: '$TAG'" >&2; exit 2; }
    REF="v$TAG"
    ;;
  *)
    echo "использование: deploy.sh dev|prod <тег>" >&2
    exit 2
    ;;
esac

DIR="/opt/trenio/$ENV_NAME"
cd "$DIR"

# Два деплоя одного окружения одновременно не запускаем
exec 9>"$DIR/.deploy.lock"
flock -n 9 || { echo "деплой $ENV_NAME уже идёт" >&2; exit 1; }

PREV_TAG="$(sed -n 's/^TRENIO_TAG=//p' .env)"
echo "==> $ENV_NAME: ${PREV_TAG:-<нет>} -> $TAG"

echo "==> compose.yaml из $REF"
curl -fsSL "$REPO_RAW/$REF/compose.yaml" -o compose.yaml.new
mv compose.yaml.new compose.yaml

if [[ "$ENV_NAME" == prod ]]; then
  BACKUP="$BACKUP_DIR/prod-$(date -u +%Y%m%dT%H%M%SZ)-${PREV_TAG:-none}.dump"
  echo "==> бэкап базы: $BACKUP"
  docker exec trenio-postgres pg_dump -U postgres -Fc trenio_prod > "$BACKUP"
  # Храним только последние KEEP_BACKUPS бэкапов
  ls -1t "$BACKUP_DIR"/prod-*.dump | tail -n +$((KEEP_BACKUPS + 1)) | xargs -r rm --
fi

# Записываем тег в .env, чтобы ручной `docker compose ...` работал с той же версией
if grep -q '^TRENIO_TAG=' .env; then
  sed -i "s/^TRENIO_TAG=.*/TRENIO_TAG=$TAG/" .env
else
  echo "TRENIO_TAG=$TAG" >> .env
fi

echo "==> pull"
docker compose pull --quiet
echo "==> up"
docker compose up -d --remove-orphans

echo "==> проверка /health"
for _ in $(seq 1 30); do
  if BODY="$(curl -fsS "http://127.0.0.1:$PORT/health" 2>/dev/null)"; then
    if [[ "$BODY" == *'"status":"ok"'* ]] && { [[ "$ENV_NAME" == dev ]] || [[ "$BODY" == *"\"version\":\"$TAG\""* ]]; }; then
      echo "$BODY"
      echo "==> $ENV_NAME обновлён до $TAG"
      exit 0
    fi
  fi
  sleep 2
done

echo "!! /health не ответил ok за 60 секунд. Последний ответ: ${BODY:-<нет>}" >&2
docker compose ps >&2
docker compose logs --tail 50 migrate backend >&2
echo "!! Откат: sudo -u deploy $0 $ENV_NAME $PREV_TAG" >&2
exit 1
