"""Ошибки из Mini App: приходят админам в Telegram, чтобы о сбое узнать раньше тренера.

Одинаковые ошибки склеиваются: одна и та же уходит не чаще раза в 10 минут,
а всего не больше 30 сообщений в час, даже если что-то сломалось у всех сразу.
Учёт в памяти процесса: после перезапуска счёт начинается заново, это не страшно.
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

SAME_ERROR_PAUSE = timedelta(minutes=10)
HOURLY_LIMIT = 30


@dataclass
class Limiter:
    last_sent: dict[str, datetime] = field(default_factory=dict)
    sent: deque[datetime] = field(default_factory=deque)

    def allow(self, key: str, now: datetime) -> bool:
        while self.sent and now - self.sent[0] >= timedelta(hours=1):
            self.sent.popleft()
        last = self.last_sent.get(key)
        if last is not None and now - last < SAME_ERROR_PAUSE:
            return False
        if len(self.sent) >= HOURLY_LIMIT:
            return False
        self.last_sent[key] = now
        self.sent.append(now)
        # Старые ключи больше не нужны: держим словарь маленьким
        for old in [k for k, at in self.last_sent.items() if now - at >= SAME_ERROR_PAUSE]:
            del self.last_sent[old]
        return True


limiter = Limiter()


def error_text(
    *,
    message: str,
    stack: str | None,
    screen: str | None,
    user_id: int,
    role: str,
    version: str,
    env: str,
) -> str:
    """Текст сообщения админу. Только внутренний номер пользователя, без имён и данных клиентов."""
    lines = [
        f"Ошибка в Mini App ({env}, {version})",
        f"Пользователь #{user_id}, {role}",
    ]
    if screen:
        lines.append(f"Где: {screen}")
    lines.append(f"Ошибка: {message}")
    if stack:
        # Первые строки стека обычно показывают место, остальное шум
        lines.append("\n".join(stack.splitlines()[:6]))
    return "\n".join(lines)[:3500]
