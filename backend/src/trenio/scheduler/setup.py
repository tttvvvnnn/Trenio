from apscheduler.schedulers.asyncio import AsyncIOScheduler


def create_scheduler() -> AsyncIOScheduler:
    # Задачи появятся на этапе 7 (напоминания). Они будут забирать записи из таблицы
    # notifications через SELECT ... FOR UPDATE SKIP LOCKED, поэтому планировщик
    # можно безопасно вынести в отдельный контейнер или запустить в двух экземплярах.
    return AsyncIOScheduler(timezone="UTC")
