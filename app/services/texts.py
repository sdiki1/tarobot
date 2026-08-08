"""Редактируемые тексты и настройки (таблица settings). Кнопки меню меняются из админки."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Setting

DEFAULTS = {
    "btn_daily": "🃏 Карта дня",
    "btn_tarot": "🔮 Расклады Таро",
    "btn_natal": "✨ Натальная карта",
    "btn_results": "📜 Мои результаты",
    "btn_support": "🆘 Поддержка",
    "btn_terms": "📄 Условия использования",
    "btn_privacy": "🔒 Политика конфиденциальности",
    "welcome_text": (
        "Добро пожаловать! Этот бот делает расклады Таро и рассчитывает натальные карты "
        "с персональной интерпретацией.\n\nМатериалы носят информационно-развлекательный "
        "характер и не заменяют профессиональную консультацию."
    ),
    "consent_text": (
        "Перед началом работы ознакомьтесь с условиями использования (/terms) и политикой "
        "конфиденциальности (/privacy) и подтвердите согласие на обработку данных."
    ),
    "terms_text": "Текст условий использования предоставляет Заказчик. /paysupport — поддержка по оплате.",
    "privacy_text": "Текст политики конфиденциальности предоставляет Заказчик.",
    "docs_version": "1.0",
    "support_text": "По вопросам работы бота и оплат напишите: @support (замените в админке).",
    "paysupport_text": (
        "Поддержка по оплатам. Опишите проблему и приложите дату оплаты — мы разберёмся "
        "и при необходимости выполним возврат. Контакт: @support."
    ),
    "daily_reversed_enabled": "true",
    "daily_ai_enabled": "true",
    "service_disclaimer": (
        "⚠️ Результат носит информационно-развлекательный характер и не является медицинской, "
        "юридической, психологической или финансовой консультацией."
    ),
    "generation_in_progress": "✨ Ваш результат формируется, обычно это занимает до минуты…",
}


async def get_setting(session: AsyncSession, key: str) -> str:
    row = await session.get(Setting, key)
    return row.value if row else DEFAULTS.get(key, "")


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    row = await session.get(Setting, key)
    if row:
        row.value = value
    else:
        session.add(Setting(key=key, value=value))
