"""Редактируемые тексты и настройки (таблица settings). Кнопки меню меняются из админки."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Setting

DEFAULTS = {
    "btn_daily": "🃏 Карта дня",
    "btn_tarot": "🔮 Расклады Таро",
    "btn_natal": "✨ Натальная карта",
    "btn_results": "📜 Мои результаты",
    "btn_support": "🆘 Поддержка",
    "btn_start": "НАЧАТЬ",
    "btn_calculate": "РАССЧИТАТЬ",
    "welcome_text": (
        "🔮Добро пожаловать!\n"
        "🤖Этот бот дает ответы на все ваши вопросы с помощью натальных карт и карт таро🎴\n"
        "<i>*Информация носит общий характер и не заменяет индивидуальные консультации.</i>"
    ),
    # Плейсхолдеры {terms}, {privacy}, {pd_consent} заменяются названиями документов;
    # если задана ссылка (*_url) — название становится ссылкой на документ.
    "consent_text": (
        "▶️Нажимая кнопку НАЧАТЬ, вы соглашаетесь с {terms}, {privacy} "
        "и подтверждаете {pd_consent}."
    ),
    # Ссылки на документы (например, Google Диск). Пусто — показывается текст-заглушка.
    "terms_url": "",
    "privacy_url": "",
    "pd_consent_url": "",
    "terms_text": "Текст условий использования предоставляет Заказчик. /paysupport — поддержка по оплате.",
    "privacy_text": "Текст политики конфиденциальности предоставляет Заказчик.",
    "pd_consent_text": "Текст согласия на обработку персональных данных предоставляет Заказчик.",
    "natal_menu_text": "✨ <b>Натальная карта</b>\nВыберите, что хотите рассчитать:",
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


# Документы: ключ -> (название в родительном/творительном падеже для текста согласия,
# заголовок, команда)
DOCUMENTS = {
    "terms": ("условиями использования", "Условия использования", "/terms"),
    "privacy": ("политикой конфиденциальности", "Политика конфиденциальности", "/privacy"),
    "pd_consent": ("согласие на обработку персональных данных",
                   "Согласие на обработку персональных данных", "/pd_consent"),
}


def _valid_url(url: str) -> bool:
    return url.startswith(("https://", "http://")) and '"' not in url


async def render_consent_text(session: AsyncSession) -> str:
    """Текст согласия под приветствием: названия документов — ссылки, если заданы URL."""
    text = await get_setting(session, "consent_text")
    for key, (phrase, _title, command) in DOCUMENTS.items():
        url = (await get_setting(session, f"{key}_url")).strip()
        if _valid_url(url):
            part = f'<a href="{url}">{phrase}</a>'
        else:
            part = f"{phrase} ({command})"
        text = text.replace("{" + key + "}", part)
    return text


async def render_document(session: AsyncSession, key: str) -> str:
    """Ответ на /terms, /privacy, /pd_consent: ссылка на документ либо текст-заглушка."""
    _phrase, title, _command = DOCUMENTS[key]
    url = (await get_setting(session, f"{key}_url")).strip()
    if _valid_url(url):
        return f'📄 {title}: <a href="{url}">открыть документ</a>'
    return await get_setting(session, f"{key}_text")
