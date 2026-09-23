"""Редактируемые тексты и настройки (таблица settings).

Всё, что бот пишет пользователю, собрано здесь по разделам и меняется в админке
(«Тексты бота»). В таблице хранятся только изменённые значения, остальные берутся
из значений по умолчанию ниже.
"""
import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Setting
from app.services.telegram_html import MESSAGE_LIMIT, clean_telegram_html, visible_text

ALERT_LIMIT = 200  # всплывающие уведомления Telegram


@dataclass(frozen=True)
class TextItem:
    key: str
    label: str
    default: str
    # html — сообщение с форматированием; plain — короткий текст без форматирования
    # (всплывающие уведомления, статусы); button — надпись на кнопке; prompt — инструкция
    # для ИИ; flag — вкл/выкл; line — строка настройки; url — ссылка
    kind: str = "html"
    hint: str = ""
    placeholders: tuple[str, ...] = ()


@dataclass(frozen=True)
class TextGroup:
    id: str
    title: str
    items: tuple[TextItem, ...]


# Подстановки в текстах: {name} -> значение при отправке
PLACEHOLDERS = {
    "order_id": "номер заказа",
    "price": "сумма в звёздах",
    "error": "причина, по которой промокод не подошёл",
    "min": "минимальная сумма заказа",
    "card": "название карты",
    "reversed": "пометка «перевёрнутая» (пусто для прямой карты)",
    "status": "статус заказа",
    "word": "кодовое слово для удаления данных",
    "terms": "ссылка «условиями использования»",
    "privacy": "ссылка «политикой конфиденциальности»",
    "pd_consent": "ссылка «согласие на обработку персональных данных»",
}

MENU_HINT = "Пользователи увидят новую надпись после /start."

TEXT_GROUPS: tuple[TextGroup, ...] = (
    TextGroup("start", "🏠 Старт и главное меню", (
        TextItem("welcome_text", "Приветствие", (
            "🔮Добро пожаловать!\n"
            "🤖Этот бот дает ответы на все ваши вопросы с помощью натальных карт и карт таро🎴\n"
            "<i>*Информация носит общий характер и не заменяет индивидуальные консультации.</i>"
        ), hint="Отправляется с картинкой. Вместе с текстом согласия — до 1024 символов, "
                "иначе картинка уйдёт отдельным сообщением."),
        TextItem("consent_text", "Согласие с документами", (
            "▶️Нажимая кнопку НАЧАТЬ, вы соглашаетесь с {terms}, {privacy} "
            "и подтверждаете {pd_consent}."
        ), hint="Показывается под приветствием, пока пользователь не нажал кнопку. "
                "Ссылки на документы задаются в разделе «Документы».",
            placeholders=("terms", "privacy", "pd_consent")),
        TextItem("btn_start", "Кнопка согласия", "НАЧАТЬ", "button"),
        TextItem("main_menu_text", "После нажатия кнопки согласия", "Главное меню 👇"),
        TextItem("btn_daily", "Кнопка меню: карта дня", "🃏 Карта дня", "button", MENU_HINT),
        TextItem("btn_tarot", "Кнопка меню: Таро", "🔮 Расклады Таро", "button", MENU_HINT),
        TextItem("btn_natal", "Кнопка меню: натальная карта", "✨ Натальная карта", "button",
                 MENU_HINT),
        TextItem("btn_results", "Кнопка меню: результаты", "📜 Мои результаты", "button",
                 MENU_HINT),
        TextItem("btn_support", "Кнопка меню: поддержка", "🆘 Поддержка", "button", MENU_HINT),
        TextItem("help_text", "Ответ на /help", (
            "Доступные команды:\n"
            "/start — главное меню\n/terms — условия использования\n"
            "/privacy — политика конфиденциальности\n"
            "/pd_consent — согласие на обработку персональных данных\n"
            "/paysupport — поддержка по оплате\n"
            "/unsubscribe — отказ от рассылок\n/delete_my_data — удаление данных"
        )),
    )),
    TextGroup("daily", "🃏 Карта дня", (
        TextItem("daily_header", "Заголовок карты дня", "🃏 Карта дня: <b>{card}</b>{reversed}",
                 placeholders=("card", "reversed")),
        TextItem("daily_reversed_mark", "Пометка перевёрнутой карты", "(перевёрнутая)",
                 hint="Подставляется в заголовок вместо {reversed} через пробел."),
        TextItem("daily_repeat_note", "Если карту дня уже получали сегодня",
                 "<i>Новая карта будет доступна завтра.</i>"),
        TextItem("daily_fallback", "Толкование, если ИИ недоступен и в колоде нет значения",
                 "Прислушайтесь к себе сегодня."),
        TextItem("daily_unavailable", "Колода недоступна",
                 "Колода карт временно недоступна. Пожалуйста, попробуйте ещё раз позже."),
        TextItem("daily_ai_prompt", "Инструкция для ИИ", (
            "Ты — доброжелательный таролог. Дай краткое значение карты дня, "
            "совет на день и одну рекомендацию-предупреждение. До 700 символов, "
            "по-русски, без медицинских и финансовых советов."
        ), "prompt"),
        TextItem("daily_ai_enabled", "Толкование карты дня от ИИ", "true", "flag"),
        TextItem("daily_reversed_enabled", "Перевёрнутые карты в карте дня", "true", "flag"),
    )),
    TextGroup("tarot", "🔮 Расклады Таро", (
        TextItem("tarot_menu_text", "Выбор расклада", "🔮 Выберите расклад:"),
        TextItem("tarot_empty", "Каталог пуст", "Каталог пока пуст."),
        TextItem("field_question", "Запрос: вопрос", "Сформулируйте ваш вопрос:"),
        TextItem("field_name", "Запрос: имя", "Введите ваше имя:"),
        TextItem("field_birth_date", "Запрос: дата рождения",
                 "Введите вашу дату рождения (ДД.ММ.ГГГГ):"),
        TextItem("field_partner_name", "Запрос: имя партнёра", "Введите имя другого человека:"),
        TextItem("field_situation", "Запрос: ситуация", "Опишите ситуацию:"),
        TextItem("field_comment", "Запрос: комментарий",
                 "Дополнительные комментарии (или «-», если нет):"),
    )),
    TextGroup("natal", "✨ Натальная карта", (
        TextItem("natal_menu_text", "Меню раздела",
                 "✨ <b>Натальная карта</b>\nВыберите, что хотите рассчитать:"),
        TextItem("btn_calculate", "Кнопка в карточке услуги", "РАССЧИТАТЬ", "button",
                 "Для услуг, у которых в карточке не задана своя кнопка."),
        TextItem("natal_unavailable", "Раздел недоступен (нет модуля расчёта)",
                 "Раздел «Натальная карта» временно недоступен. Загляните позже 🙏"),
        TextItem("natal_empty", "Нет активных услуг",
                 "Услуга «Натальная карта» временно недоступна."),
        TextItem("natal_ask_name", "Запрос имени", "Введите имя или обозначение профиля:"),
        TextItem("natal_ask_name_pair", "Запрос имени (совместимость)", (
            "Для расчёта нужны данные рождения двух человек.\n\n"
            "Сначала ваши данные. Введите ваше имя:"
        )),
        TextItem("natal_ask_partner_name", "Запрос имени второго человека",
                 "Отлично! Теперь данные второго человека.\nВведите его имя:"),
        TextItem("natal_name_invalid", "Имя не текстом", "Введите имя текстом:"),
        TextItem("natal_ask_birth_date", "Запрос даты рождения",
                 "Введите дату рождения (ДД.ММ.ГГГГ):"),
        TextItem("natal_date_format_error", "Дата в неверном формате",
                 "Неверный формат. Пример: 21.03.1990"),
        TextItem("natal_date_invalid", "Дата вне допустимого диапазона",
                 "Проверьте дату рождения. Пример: 21.03.1990"),
        TextItem("natal_ask_accuracy", "Вопрос о точности времени",
                 "Насколько точно известно время рождения?"),
        TextItem("btn_acc_exact", "Кнопка: точное время", "⏱ Точное время до минуты", "button"),
        TextItem("btn_acc_hour", "Кнопка: примерный час", "🕐 Известен примерный час", "button"),
        TextItem("btn_acc_unknown", "Кнопка: время неизвестно", "❓ Время неизвестно", "button"),
        TextItem("natal_ask_time", "Запрос точного времени", "Введите время рождения (ЧЧ:ММ):"),
        TextItem("natal_ask_hour", "Запрос примерного часа", (
            "Введите примерный час рождения (например, 14):\n"
            "<i>Расчёт будет выполнен на середину часа; дома и Асцендент — с возможной "
            "погрешностью.</i>"
        )),
        TextItem("natal_time_format_error", "Время в неверном формате",
                 "Неверный формат. Пример: 14:30 (или просто 14 для часа)."),
        TextItem("natal_ask_place", "Запрос места рождения", "Введите населённый пункт рождения:"),
        TextItem("natal_ask_place_no_time", "Запрос места рождения (время неизвестно)", (
            "Введите населённый пункт рождения:\n"
            "<i>Без времени рождения Асцендент и дома не рассчитываются, разбор будет "
            "ограниченным.</i>"
        )),
        TextItem("natal_place_not_found", "Место не найдено",
                 "Населённый пункт не найден. Уточните название:"),
        TextItem("natal_place_choose", "Несколько вариантов места",
                 "Найдено несколько вариантов, выберите нужный:"),
        TextItem("natal_geocoder_error", "Поиск места недоступен",
                 "Сервис геокодинга временно недоступен, попробуйте позже."),
    )),
    TextGroup("order", "💳 Заказ, промокод и оплата", (
        TextItem("price_line", "Строка цены в карточке услуги", "Стоимость: {price} ⭐",
                 placeholders=("price",)),
        TextItem("order_created", "Заказ создан", "Заказ №{order_id} создан. Сумма: {price} ⭐",
                 placeholders=("order_id", "price")),
        TextItem("btn_promo_enter", "Кнопка: ввести промокод", "🎟 Ввести промокод", "button"),
        TextItem("btn_pay", "Кнопка: оплата", "💳 Перейти к оплате", "button"),
        TextItem("promo_ask", "Запрос промокода", "Введите промокод:"),
        TextItem("promo_applied", "Промокод применён", "✅ Промокод применён. Итог: {price} ⭐",
                 placeholders=("price",)),
        TextItem("promo_error", "Промокод не подошёл", "❌ {error}", placeholders=("error",),
                 hint="Вместо {error} подставляется одна из причин ниже."),
        TextItem("promo_err_not_found", "Причина: не найден",
                 "Промокод не найден или не активен."),
        TextItem("promo_err_not_started", "Причина: ещё не действует",
                 "Промокод ещё не действует."),
        TextItem("promo_err_expired", "Причина: истёк", "Срок действия промокода истёк."),
        TextItem("promo_err_wrong_service", "Причина: другая услуга",
                 "Промокод не действует для этой услуги."),
        TextItem("promo_err_min_sum", "Причина: мала сумма заказа",
                 "Минимальная сумма заказа для промокода — {min} ⭐.", placeholders=("min",)),
        TextItem("promo_err_limit", "Причина: исчерпан лимит",
                 "Лимит активаций промокода исчерпан."),
        TextItem("promo_err_used", "Причина: уже использован",
                 "Вы уже использовали этот промокод."),
        TextItem("generation_in_progress", "После оплаты",
                 "✨ Ваш результат формируется, обычно это занимает до минуты…"),
        TextItem("alert_service_unavailable", "Уведомление: услуга недоступна",
                 "Услуга временно недоступна", "plain"),
        TextItem("alert_daily_limit", "Уведомление: дневной лимит",
                 "Достигнут дневной лимит по этой услуге. Попробуйте завтра.", "plain"),
        TextItem("alert_order_not_found", "Уведомление: заказ не найден", "Заказ не найден",
                 "plain"),
        TextItem("checkout_err_invalid", "Ошибка оплаты: некорректный заказ",
                 "Некорректный заказ.", "plain"),
        TextItem("checkout_err_paid", "Ошибка оплаты: заказ уже оплачен",
                 "Заказ не найден или уже оплачен.", "plain"),
        TextItem("checkout_err_amount", "Ошибка оплаты: сумма изменилась",
                 "Сумма заказа изменилась, создайте заказ заново.", "plain"),
    )),
    TextGroup("results", "📜 Результаты и заказы", (
        TextItem("service_disclaimer", "Предупреждение под результатом", (
            "⚠️ Результат носит информационно-развлекательный характер и не является "
            "медицинской, юридической, психологической или финансовой консультацией."
        )),
        TextItem("generation_failed", "Не удалось подготовить результат", (
            "К сожалению, при формировании результата произошла ошибка. "
            "Мы уже разбираемся; поддержка: /paysupport"
        )),
        TextItem("results_title", "Список заказов", "📜 Последние заказы:"),
        TextItem("results_empty", "Заказов нет", "У вас пока нет заказов."),
        TextItem("result_not_ready", "Результат ещё не готов",
                 "Заказ №{order_id}: {status}. Результат пока не готов.",
                 placeholders=("order_id", "status")),
        TextItem("status_created", "Статус: создан", "создан", "plain"),
        TextItem("status_invoiced", "Статус: ждёт оплаты", "ожидает оплаты", "plain"),
        TextItem("status_paid", "Статус: оплачен", "оплачен, готовится", "plain"),
        TextItem("status_completed", "Статус: готов", "готов", "plain"),
        TextItem("status_failed", "Статус: ошибка", "ошибка", "plain"),
        TextItem("status_refunded", "Статус: возврат", "возврат", "plain"),
        TextItem("status_cancelled", "Статус: отменён", "отменён", "plain"),
    )),
    TextGroup("support", "🆘 Поддержка, рассылки и данные", (
        TextItem("support_text", "Кнопка «Поддержка»",
                 "По вопросам работы бота и оплат напишите: @support (замените в админке)."),
        TextItem("paysupport_text", "Ответ на /paysupport", (
            "Поддержка по оплатам. Опишите проблему и приложите дату оплаты — мы разберёмся "
            "и при необходимости выполним возврат. Контакт: @support."
        )),
        TextItem("unsubscribe_done", "/unsubscribe: отписка", (
            "Вы отписаны от рекламных рассылок. Сообщения по вашим заказам "
            "будут приходить по-прежнему. Подписаться снова: /unsubscribe"
        )),
        TextItem("subscribe_done", "/unsubscribe: повторная подписка",
                 "Вы снова подписаны на рассылки. Отписаться: /unsubscribe"),
        TextItem("btn_unsubscribe", "Кнопка под рассылкой", "🔕 Отписаться", "button"),
        TextItem("alert_unsubscribed", "Уведомление после отписки", "Вы отписаны от рассылок",
                 "plain"),
        TextItem("delete_prompt", "/delete_my_data: подтверждение", (
            "Вы запросили удаление персональных данных: профиль, вопросы, данные рождения, "
            "сохранённые результаты и настройки рассылок будут удалены. Платёжные сведения "
            "сохраняются в минимально необходимом объёме для возвратов и учёта.\n\n"
            "Для подтверждения отправьте слово: {word}"
        ), placeholders=("word",)),
        TextItem("delete_confirm_word", "Кодовое слово для удаления", "УДАЛИТЬ", "line",
                 "Регистр букв не важен."),
        TextItem("delete_cancelled", "Удаление отменено", "Удаление отменено."),
        TextItem("delete_done", "Данные удалены", "Ваши персональные данные удалены/обезличены."),
    )),
    TextGroup("docs", "📄 Документы", (
        TextItem("terms_url", "Ссылка: условия использования", "", "url",
                 "Например, на Google Диск. Пусто — бот покажет текст ниже."),
        TextItem("terms_text", "Условия использования (если нет ссылки)",
                 "Текст условий использования предоставляет Заказчик. "
                 "/paysupport — поддержка по оплате."),
        TextItem("privacy_url", "Ссылка: политика конфиденциальности", "", "url"),
        TextItem("privacy_text", "Политика конфиденциальности (если нет ссылки)",
                 "Текст политики конфиденциальности предоставляет Заказчик."),
        TextItem("pd_consent_url", "Ссылка: согласие на обработку данных", "", "url"),
        TextItem("pd_consent_text", "Согласие на обработку данных (если нет ссылки)",
                 "Текст согласия на обработку персональных данных предоставляет Заказчик."),
        TextItem("docs_version", "Версия документов", "1.0", "line",
                 "Смените версию, чтобы все пользователи заново приняли документы."),
    )),
)

TEXTS = {item.key: item for group in TEXT_GROUPS for item in group.items}
DEFAULTS = {key: item.default for key, item in TEXTS.items()}

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def render(template: str, **values) -> str:
    """Подставляет {name}; неизвестные подстановки и прочие скобки остаются как есть."""
    return _PLACEHOLDER.sub(
        lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), template)


async def get_setting(session: AsyncSession, key: str) -> str:
    row = await session.get(Setting, key)
    return row.value if row else DEFAULTS.get(key, "")


async def get_text(session: AsyncSession, key: str, **values) -> str:
    return render(await get_setting(session, key), **values)


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    row = await session.get(Setting, key)
    if row:
        row.value = value
    else:
        session.add(Setting(key=key, value=value))


async def save_text(session: AsyncSession, key: str, value: str) -> None:
    """Значение по умолчанию не хранится — тогда до бота доходят обновления стандартных
    текстов."""
    if value != DEFAULTS.get(key):
        await set_setting(session, key, value)
    elif row := await session.get(Setting, key):
        await session.delete(row)


def validate_text(item: TextItem, raw: str) -> tuple[str, list[str]]:
    """Проверка значения из админки. Возвращает (значение для сохранения, ошибки)."""
    value = raw.replace("\r\n", "\n").replace("\r", "\n").strip()
    if item.kind == "flag":
        return ("true" if value == "true" else "false"), []
    if item.kind == "url":
        if value and not _valid_url(value):
            return value, ["Ссылка должна начинаться с https:// или http://."]
        return value, []
    if not value:
        return value, ["Текст не может быть пустым."]
    if item.kind == "html":
        value, errors = clean_telegram_html(value)
        if len(visible_text(value)) > MESSAGE_LIMIT:
            errors.append(f"Сообщение длиннее {MESSAGE_LIMIT} символов — Telegram его не примет.")
        return value, errors
    if item.kind in ("button", "plain", "line"):
        value = " ".join(value.split())
    if item.kind == "plain" and len(value) > ALERT_LIMIT:
        return value, [f"Не длиннее {ALERT_LIMIT} символов (ограничение Telegram)."]
    return value, []


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
