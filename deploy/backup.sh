#!/usr/bin/env bash
# Ежедневный бэкап prod базы. Лежит в /opt/trenio/bin/backup.sh (владелец root),
# запускает его таймер systemd trenio-backup.timer.
#
# 1. pg_dump trenio_prod в /opt/trenio/backups/daily, храним KEEP_LOCAL последних
# 2. проверка, что файл читается (pg_restore --list)
# 3. копия вне сервера: файл, зашифрованный gpg, prod-бот присылает в чат админа
# 4. пинг push-монитора Uptime Kuma: не было пинга сутки или пришёл down — придёт алерт
#
# Вручную: sudo /opt/trenio/bin/backup.sh
set -euo pipefail

DB=trenio_prod
DIR=/opt/trenio/backups/daily
KEEP_LOCAL=7
# Токен prod-бота берём из .env prod, чтобы не хранить секрет второй раз
PROD_ENV=/opt/trenio/prod/.env
# Пароль шифрования копии, которая уходит в Telegram (одна строка, только для root)
PASS_FILE=/opt/trenio/bin/backup.pass
# Бот может отправить файл не больше 50 МБ
TG_LIMIT_BYTES=$((50 * 1024 * 1024))

# То, чего нет в репозитории (чат админа, адрес push-монитора), лежит на сервере
CONF=/opt/trenio/bin/backup.env
if [[ -f "$CONF" ]]; then
  source "$CONF"
fi
TG_CHAT_ID="${TG_CHAT_ID:-}"   # твой Telegram ID
PUSH_URL="${PUSH_URL:-}"       # https://<домен Kuma>/api/push/<токен монитора>

# push up|down "сообщение": отметка в push-мониторе Uptime Kuma
push() {
  if [[ -n "$PUSH_URL" ]]; then
    curl -fsS -m 10 --retry 3 -G "$PUSH_URL" \
      --data-urlencode "status=$1" --data-urlencode "msg=$2" > /dev/null || true
  fi
}
# Любая упавшая команда: сразу сообщаем Kuma, алерт придёт не через сутки, а сейчас
trap 'push down "бэкап упал на строке $LINENO"' ERR

# В дампе персональные данные клиентов: каталог только для root
install -d -m 700 "$DIR"
# Остатки прошлого неудачного запуска
rm -f "$DIR"/*.part "$DIR"/*.gpg
NAME="prod-daily-$(date -u +%Y%m%dT%H%M%SZ).dump"
FILE="$DIR/$NAME"
echo "==> pg_dump $DB -> $FILE"
# Пишем во временный файл: оборванный дамп не должен выглядеть готовым
docker exec trenio-postgres pg_dump -U postgres -Fc "$DB" > "$FILE.part"
mv "$FILE.part" "$FILE"

echo "==> проверка, что файл читается"
docker exec -i trenio-postgres pg_restore --list < "$FILE" > /dev/null
SIZE="$(du -h "$FILE" | cut -f1)"
echo "    размер: $SIZE"

ls -1t "$DIR"/prod-daily-*.dump | tail -n +$((KEEP_LOCAL + 1)) | xargs -r rm --

if [[ -n "$TG_CHAT_ID" ]]; then
  echo "==> шифрование и отправка в Telegram"
  gpg --batch --yes --quiet --symmetric --cipher-algo AES256 \
    --passphrase-file "$PASS_FILE" -o "$FILE.gpg" "$FILE"
  if (( $(stat -c %s "$FILE.gpg") > TG_LIMIT_BYTES )); then
    echo "!! $NAME.gpg больше 50 МБ, Telegram его не примет: пора переходить на облако" >&2
    false
  fi
  TOKEN="$(sed -n 's/^BOT_TOKEN=//p' "$PROD_ENV" | tr -d "\"'")"
  # Токен передаём curl через stdin, а не аргументом: аргументы видны всем в ps
  printf 'url = "https://api.telegram.org/bot%s/sendDocument"\n' "$TOKEN" |
    curl -fsS -m 120 --retry 3 -K - \
      -F chat_id="$TG_CHAT_ID" \
      -F disable_notification=true \
      -F caption="Бэкап prod $(date +%d.%m.%Y), $SIZE" \
      -F document=@"$FILE.gpg;filename=$NAME.gpg" > /dev/null
  rm -f "$FILE.gpg"
fi

push up "OK, $SIZE"
echo "==> готово"
