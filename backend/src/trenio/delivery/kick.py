"""Сигнал «в очереди появилось срочное уведомление».

Сервисы зовут kick() после коммита, чтобы событие ушло сразу, а не через минуту.
Если отправщик работает в этом процессе, он регистрирует здесь свой запуск;
в процессе без планировщика kick() ничего не делает, и сообщение заберёт плановый проход.
Модуль без зависимостей, чтобы сервисы не тянули за собой бота.
"""

from collections.abc import Callable

_hook: Callable[[], None] | None = None


def register(hook: Callable[[], None] | None) -> None:
    global _hook
    _hook = hook


def kick() -> None:
    if _hook is not None:
        _hook()
