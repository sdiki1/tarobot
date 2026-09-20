"""Первичное заполнение БД: 78 карт Таро, стартовые услуги с промптами.

Запуск: docker compose run --rm bot python -m scripts.seed
"""
import asyncio

from sqlalchemy import select

from app.db.models import Service, ServicePrompt, ServiceType, TarotCard
from app.db.session import SessionMaker
from app.tarot.deck import build_deck

BASE_SYSTEM_PROMPT = (
    "Ты — опытный таролог. Интерпретируй ТОЛЬКО переданные карты, не выбирай свои. "
    "Отвечай по-русски, тепло и уважительно. Структура: значение каждой позиции, "
    "общий вывод, рекомендации. Не давай медицинских, юридических и финансовых советов, "
    "не предсказывай смерть и болезни."
)

SERVICES = [
    dict(code="one_card", title="Ответ одной картой", price_stars=50, cards_count=1,
         positions=["Ответ"], description="Быстрый ответ на ваш вопрос по одной карте.",
         sort_order=10),
    dict(code="situation", title="Расклад на ситуацию", price_stars=150, cards_count=3,
         positions=["Прошлое", "Настоящее", "Будущее"],
         description="Три карты: истоки ситуации, текущее положение и вероятное развитие.",
         sort_order=20),
    dict(code="relations", title="Расклад на отношения", price_stars=200, cards_count=4,
         positions=["Вы", "Партнёр", "Отношения сейчас", "Перспектива"],
         required_fields=["question", "name", "partner_name"],
         description="Четыре карты о вас, партнёре и перспективах отношений.",
         sort_order=30),
    dict(code="near_future", title="Ближайшее будущее", price_stars=150, cards_count=3,
         positions=["Сейчас", "Через месяц", "Через три месяца"],
         description="Что ждёт вас в ближайшие месяцы.", sort_order=40),
    # --- Раздел «Натальная карта» ---
    # required_fields: partner — сбор данных второго человека, transits — транзиты на год.
    dict(code="natal_year", title="🔮 Астрологический прогноз на год", price_stars=400,
         cards_count=0, type=ServiceType.natal, requires_question=False, positions=[],
         required_fields=["transits"],
         description=(
             "Какие темы выйдут на первый план: любовь, работа или личные перемены? "
             "Посмотрите астрологический прогноз по вашей натальной карте с ключевыми "
             "периодами года и подсказками, на что обратить внимание."),
         focus=(
             "Задача: астрологический прогноз на ближайшие 12 месяцев. Опирайся на переданные "
             "транзиты медленных планет к натальной карте. Структура: главные темы года "
             "(любовь, работа, личные перемены), ключевые периоды по месяцам, на что обратить "
             "внимание. Формулируй как тенденции и подсказки, а не как гарантированные события."),
         sort_order=51),
    dict(code="natal_compat", title="❤️ Гороскоп совместимости", price_stars=500,
         cards_count=0, type=ServiceType.natal, requires_question=False, positions=[],
         required_fields=["partner"],
         description=(
             "Что вас притягивает друг к другу, а в чём бывает сложно найти общий язык? "
             "Разбор ваших карт поможет взглянуть на чувства, общение и ожидания в паре — "
             "и лучше понять ваши различия."),
         focus=(
             "Задача: разбор совместимости двух людей по их натальным картам и аспектам "
             "синастрии. Структура: что притягивает друг к другу, чувства и эмоции, общение, "
             "ожидания в паре, зоны напряжения и как с ними обходиться. Не выноси вердиктов "
             "«подходите/не подходите», не советуй расставаться или вступать в брак."),
         sort_order=52),
    dict(code="natal_purpose", title="✨ Ваше предназначение по гороскопу", price_stars=400,
         cards_count=0, type=ServiceType.natal, requires_question=False, positions=[],
         description=(
             "Какие таланты стоит раскрыть и в каких занятиях искать вдохновение? "
             "Исследуйте свои сильные стороны и возможные пути самореализации через "
             "символику натальной карты."),
         focus=(
             "Задача: разбор предназначения и самореализации. Структура: врождённые таланты, "
             "сильные стороны, занятия и сферы, где человек находит вдохновение, возможные "
             "пути самореализации, что мешает раскрыться и как это смягчить."),
         sort_order=53),
    dict(code="natal_career", title="💼 Работа и финансы по гороскопу", price_stars=400,
         cards_count=0, type=ServiceType.natal, requires_question=False, positions=[],
         description=(
             "Какой формат работы вам ближе и что помогает чувствовать уверенность в своих "
             "силах? Астрологический разбор ваших склонностей, профессиональных качеств и "
             "отношения к деньгам."),
         focus=(
             "Задача: разбор темы работы и денег. Структура: подходящий формат работы, "
             "профессиональные качества и склонности, что даёт уверенность в своих силах, "
             "отношение к деньгам. Не давай инвестиционных и финансовых рекомендаций, "
             "не называй суммы и сроки."),
         sort_order=54),
    dict(code="natal", title="🌟 Полный анализ личности по вашей дате рождения",
         price_stars=400, cards_count=0,
         type=ServiceType.natal, requires_question=False, positions=[],
         description=(
             "Ваш характер, эмоции, сильные стороны и привычные реакции в отношениях — в одном "
             "подробном астрологическом разборе. Возможность посмотреть на себя со стороны и "
             "заметить качества, которым вы раньше не придавали значения."),
         focus=(
             "Задача: полный анализ личности. Структура: общий портрет, характер "
             "(Солнце), эмоции (Луна), Асцендент (если есть), сильные стороны, привычные "
             "реакции в отношениях, ключевые аспекты, рекомендации."),
         sort_order=55),
]

NATAL_SYSTEM_PROMPT = (
    "Ты — профессиональный астролог. Интерпретируй ТОЛЬКО переданные рассчитанные "
    "астрологические данные, ничего не пересчитывай и не выдумывай положений планет. "
    "Отвечай по-русски, тепло и уважительно. "
    "Если в данных есть предупреждения о точности — обязательно упомяни их. "
    "Не давай медицинских, юридических и финансовых советов, не предсказывай смерть и болезни."
)

NATAL_USER_TEMPLATE = (
    "Рассчитанные данные:\n{facts}\n\n"
    "Дай развёрнутую интерпретацию по заданной структуре и общий вывод."
)


async def main() -> None:
    async with SessionMaker() as session:
        existing_card_ids = set((await session.scalars(select(TarotCard.id))).all())
        missing_cards = [card for card in build_deck() if card["id"] not in existing_card_ids]
        for card in missing_cards:
            session.add(TarotCard(**card))
        if missing_cards:
            print(f"Загружено карт Таро: {len(missing_cards)}")

        for spec in SERVICES:
            if await session.scalar(select(Service).where(Service.code == spec["code"])):
                continue
            spec = dict(spec)
            focus = spec.pop("focus", "")
            service = Service(**spec)
            session.add(service)
            await session.flush()
            if service.type == ServiceType.natal:
                system_prompt = f"{NATAL_SYSTEM_PROMPT}\n\n{focus}".strip()
                template = NATAL_USER_TEMPLATE
            else:
                system_prompt = BASE_SYSTEM_PROMPT
                template = (
                    "Данные:\n{facts}\n\nВопрос пользователя: {question}\n\n"
                    "Дай развёрнутую интерпретацию каждой позиции, общий вывод и рекомендации."
                )
            session.add(ServicePrompt(
                service_id=service.id, system_prompt=system_prompt,
                user_prompt_template=template,
            ))
            print(f"Создана услуга: {service.title}")
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
