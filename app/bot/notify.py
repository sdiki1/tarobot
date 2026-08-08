"""Служебные уведомления администраторам в Telegram."""
import logging

from aiogram import Bot

from app.config import get_settings

log = logging.getLogger(__name__)


async def notify_admins(bot: Bot, text: str) -> None:
    for admin_id in get_settings().admin_ids:
        try:
            await bot.send_message(admin_id, f"⚙️ {text}")
        except Exception:
            log.warning("Failed to notify admin %s", admin_id)
