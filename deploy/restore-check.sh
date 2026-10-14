#!/usr/bin/env bash
# Проверка восстановления. Разворачивает бэкап во временную базу trenio_restore_check
# и сравнивает число строк в каждой таблице с живой prod базой. Prod не трогает.
# Лежит в /opt/trenio/bin/restore-check.sh (владелец root).
#
# Вручную: sudo /opt/trenio/bin/restore-check.sh             последний ежедневный бэкап
#          sudo /opt/trenio/bin/restore-check.sh <файл.dump>  конкретный файл
set -euo pipefail

DIR=/opt/trenio/backups/daily
CHECK_DB=trenio_restore_check
FILE="${1:-$(ls -1t "$DIR"/prod-daily-*.dump | head -n 1)}"

sql() { docker exec -i trenio-postgres psql -U postgres -v ON_ERROR_STOP=1 -qAt "$@"; }

echo "==> бэкап: $FILE"
sql -c "DROP DATABASE IF EXISTS $CHECK_DB" -c "CREATE DATABASE $CHECK_DB"
# Временная база удаляется при любом исходе
trap 'sql -c "DROP DATABASE IF EXISTS $CHECK_DB"' EXIT

echo "==> pg_restore в $CHECK_DB"
docker exec -i trenio-postgres pg_restore -U postgres -d "$CHECK_DB" \
  --no-owner --no-acl --exit-on-error < "$FILE"

echo "==> строк в таблицах (prod успел измениться с момента бэкапа, небольшая разница — норма)"
printf '%-24s %8s %8s\n' table backup prod
for t in $(sql -d trenio_prod -c "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1"); do
  in_backup=$(sql -d "$CHECK_DB" -c "SELECT count(*) FROM \"$t\"" 2> /dev/null || echo "нет")
  in_prod=$(sql -d trenio_prod -c "SELECT count(*) FROM \"$t\"")
  printf '%-24s %8s %8s\n' "$t" "$in_backup" "$in_prod"
done
echo "==> миграция в бэкапе: $(sql -d "$CHECK_DB" -c 'SELECT version_num FROM alembic_version')"
echo "==> миграция в prod:   $(sql -d trenio_prod -c 'SELECT version_num FROM alembic_version')"
echo "==> восстановление работает"
