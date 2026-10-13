"""Точки входа: python -m trenio <команда>.

all        API, бот и планировщик в одном процессе (компактная схема)
api        только HTTP API
bot        только бот (webhook или polling)
scheduler  только планировщик
migrate    применить миграции базы до последней версии
"""

import argparse
import asyncio
import logging

import uvicorn

from trenio.api.app import ALL_COMPONENTS, Component, create_app


def run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", "trenio:migrations")
    command.upgrade(config, "head")


async def run_scheduler_forever() -> None:
    from trenio.bot.setup import get_bot
    from trenio.scheduler.setup import create_scheduler

    scheduler, _ = create_scheduler()
    scheduler.start()
    try:
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown(wait=False)
        await get_bot().session.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="trenio")
    parser.add_argument("command", choices=["all", "api", "bot", "scheduler", "migrate"])
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if args.command == "migrate":
        run_migrations()
        return
    if args.command == "scheduler":
        asyncio.run(run_scheduler_forever())
        return

    components = ALL_COMPONENTS if args.command == "all" else frozenset({Component(args.command)})
    uvicorn.run(create_app(components), host=args.host, port=args.port, proxy_headers=True)


if __name__ == "__main__":
    main()
