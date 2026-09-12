"""Совместимая с Python 3.12 точка запуска ARQ-воркера."""
import asyncio
import logging


def main() -> None:
    # ARQ 0.26 вызывает get_event_loop() при создании Worker. Начиная с
    # Python 3.12 uvloop не создаёт loop неявно, поэтому готовим его заранее.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    from arq.worker import run_worker

    from app.worker.worker import WorkerSettings

    logging.basicConfig(level=logging.INFO)
    try:
        run_worker(WorkerSettings)
    finally:
        if not loop.is_closed():
            loop.close()


if __name__ == "__main__":
    main()
