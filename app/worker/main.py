"""Совместимая с Python 3.12 точка запуска ARQ-воркера."""
import asyncio
import logging


def main() -> None:
    from arq.worker import run_worker

    from app.worker.worker import WorkerSettings

    # Импорты выше могут установить uvloop и тем самым заменить event-loop
    # policy. Поэтому loop нужно создать строго после них, перед созданием
    # ARQ Worker.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    logging.basicConfig(level=logging.INFO)
    try:
        run_worker(WorkerSettings)
    finally:
        if not loop.is_closed():
            loop.close()


if __name__ == "__main__":
    main()
