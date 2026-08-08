"""Точка входа Telegram-бота (long polling)."""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.handlers import daily, natal, payments, results, start, tarot
from app.bot.middleware import DbUserMiddleware
from app.config import get_settings

logging.basicConfig(level=logging.INFO)


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.update.middleware(DbUserMiddleware())
    # Порядок важен: команды и платежи раньше текстовых кнопок
    dp.include_router(start.router)
    dp.include_router(payments.router)
    dp.include_router(daily.router)
    dp.include_router(tarot.router)
    dp.include_router(natal.router)
    dp.include_router(results.router)
    return dp


async def main() -> None:
    settings = get_settings()
    bot = Bot(settings.bot_token,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher()
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
