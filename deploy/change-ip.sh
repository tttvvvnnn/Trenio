#!/usr/bin/env bash
# Замена IP сервера в конфигах на самом сервере (после смены IP у хостера).
#
# Работает в два шага, чтобы ничего не менять вслепую:
#   1. sudo bash change-ip.sh СТАРЫЙ НОВЫЙ          — только показывает, где найден старый IP
#   2. sudo bash change-ip.sh СТАРЫЙ НОВЫЙ --apply  — бэкап найденных файлов в tar, потом замена
#
# Где ищем: /opt (Trenio, edge, стеки Docker), /etc (nginx, hosts, ufw, systemd), /root, /home.
# Что пропускаем: данные Postgres, тома Docker, бэкапы, node_modules, .git, файлы больше 5 МБ
# история shell, кэши и двоичные файлы. Сетевые настройки (/etc/netplan, /etc/network, cloud-init) скрипт
# только показывает и не трогает: ошибка там отрежет сервер от сети.
#
# После --apply скрипт печатает, какие сервисы перезапустить. Сам ничего не перезапускает.
# Откат: sudo tar -xzPf <бэкап> (путь бэкапа скрипт напечатает)
set -euo pipefail

usage() {
  echo "Использование: sudo bash $0 СТАРЫЙ_IP НОВЫЙ_IP [--apply]" >&2
  exit 2
}

[[ $# -ge 2 ]] || usage
OLD="$1"
NEW="$2"
APPLY=0
[[ "${3:-}" == "--apply" ]] && APPLY=1
[[ $# -le 3 ]] || usage

ip_re='^([0-9]{1,3}\.){3}[0-9]{1,3}$'
[[ "$OLD" =~ $ip_re && "$NEW" =~ $ip_re ]] || { echo "Это не похоже на IPv4: $OLD / $NEW" >&2; exit 2; }
[[ "$OLD" != "$NEW" ]] || { echo "Старый и новый IP совпадают" >&2; exit 2; }
[[ $EUID -eq 0 ]] || { echo "Запусти через sudo: файлы в /etc и /opt принадлежат root" >&2; exit 1; }

# Точки в IP для grep и sed экранируем, а по краям требуем «не цифру»,
# чтобы 1.2.3.4 не совпал внутри 11.2.3.45
OLD_RE="${OLD//./\\.}"
PATTERN="(^|[^0-9])${OLD_RE}([^0-9]|$)"

SEARCH_DIRS=(/opt /etc /root /home)
# Сетевые файлы: только показываем
NET_RE='^/etc/(netplan|network|cloud|NetworkManager|systemd/network)/'

GREP_EXCLUDES=(
  --exclude-dir=.git --exclude-dir=node_modules
  --exclude-dir=backups --exclude-dir=pgdata --exclude-dir=postgres-data
  --exclude-dir=volumes --exclude-dir=overlay2 --exclude-dir=containerd
  --exclude='*.dump' --exclude='*.gz' --exclude='*.gpg' --exclude='*.bak*'
  --exclude='*.log' --exclude='*.jsonl' --exclude='.*_history'
  --exclude-dir=.cache --exclude-dir=.npm --exclude-dir=.claude --exclude-dir=.vscode-server
)

echo "== Ищу $OLD в ${SEARCH_DIRS[*]} (это может занять минуту)"
mapfile -t FILES < <(
  grep -rIlE "${GREP_EXCLUDES[@]}" "$PATTERN" "${SEARCH_DIRS[@]}" 2>/dev/null \
    | while read -r f; do
        # Большие файлы — почти наверняка не конфиги
        [[ $(stat -c %s "$f") -le $((5 * 1024 * 1024)) ]] && echo "$f"
      done || true
)

EDIT=()
NET=()
for f in "${FILES[@]}"; do
  if [[ "$f" =~ $NET_RE ]]; then NET+=("$f"); else EDIT+=("$f"); fi
done

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "В файлах старый IP не найден."
else
  for f in "${EDIT[@]}"; do
    echo
    echo "--- $f"
    grep -nE "$PATTERN" "$f" | cut -c1-200
  done
  if [[ ${#NET[@]} -gt 0 ]]; then
    echo
    echo "== Сетевые настройки со старым IP. Скрипт их НЕ меняет, проверь у хостера, какой адрес и шлюз нужны:"
    for f in "${NET[@]}"; do
      echo "--- $f"
      grep -nE "$PATTERN" "$f" | cut -c1-200
    done
  fi
fi

# То, что живёт не в файлах: правила файрвола и адреса на интерфейсах
echo
echo "== Файрвол (iptables-save), строки со старым IP:"
if command -v iptables-save >/dev/null; then
  iptables-save 2>/dev/null | grep -E "$PATTERN" || echo "нет"
fi
echo
echo "== Адреса на интерфейсах сервера сейчас:"
ip -4 -brief addr show 2>/dev/null || true
if ip -4 addr show 2>/dev/null | grep -qE "inet ${NEW//./\\.}/"; then
  echo "Новый IP $NEW есть на интерфейсе, хорошо."
else
  echo "ВНИМАНИЕ: $NEW не найден на интерфейсах. Если сервер за NAT хостера, это нормально."
fi

if [[ $APPLY -eq 0 ]]; then
  echo
  echo "Это был только просмотр. Чтобы заменить в файлах выше (кроме сетевых):"
  echo "  sudo bash $0 $OLD $NEW --apply"
  exit 0
fi

if [[ ${#EDIT[@]} -eq 0 ]]; then
  echo
  echo "Менять нечего."
  exit 0
fi

BACKUP="/root/change-ip-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
# -P сохраняет абсолютные пути, тогда откат одной командой: tar -xzPf "$BACKUP"
tar -czPf "$BACKUP" "${EDIT[@]}"
chmod 600 "$BACKUP"
echo
echo "== Бэкап: $BACKUP (откат: sudo tar -xzPf $BACKUP)"


for f in "${EDIT[@]}"; do
  # sed -i пишет новый файл и подменяет старый; владелец и права при этом сохраняются
  sed -i -E "s/(^|[^0-9])${OLD_RE}([^0-9]|\$)/\1${NEW}\2/g" "$f"
  # Второй проход ловит соседние вхождения вроде "OLD,OLD", которые первый пропускает
  sed -i -E "s/(^|[^0-9])${OLD_RE}([^0-9]|\$)/\1${NEW}\2/g" "$f"
  echo "заменено: $f"
done

LEFT=$(grep -lE "$PATTERN" "${EDIT[@]}" 2>/dev/null || true)
if [[ -n "$LEFT" ]]; then
  echo "ВНИМАНИЕ: старый IP остался в: $LEFT"
fi

echo
echo "== Что перезапустить, смотря какие файлы поменялись:"
printf '%s\n' "${EDIT[@]}" | grep -q '^/opt/edge/' &&
  echo "  edge nginx:  docker exec edge nginx -t -c /etc/nginx/edge/nginx.conf && docker exec edge nginx -s reload -c /etc/nginx/edge/nginx.conf"
printf '%s\n' "${EDIT[@]}" | grep -qE '^/opt/trenio/(dev|prod)/' &&
  echo "  Trenio:      cd /opt/trenio/<dev|prod> && docker compose up -d"
printf '%s\n' "${EDIT[@]}" | grep -q '^/etc/nginx/' &&
  echo "  nginx хоста: nginx -t && systemctl reload nginx"
printf '%s\n' "${EDIT[@]}" | grep -q '^/etc/ufw/' &&
  echo "  ufw:         ufw reload"
printf '%s\n' "${EDIT[@]}" | grep -q '^/etc/ssh/' &&
  echo "  ssh:         sshd -t && systemctl reload ssh   (не закрывай текущую сессию, пока не проверишь вход в новой)"
echo "  остальные стеки в /opt: docker compose up -d в папке стека, если его файл в списке выше"
