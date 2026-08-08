"""Первичное заполнение БД: 78 карт Таро, стартовые услуги с промптами.

Запуск: docker compose run --rm bot python scripts/seed.py
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
    dict(code="natal", title="Натальная карта", price_stars=400, cards_count=0,
         type=ServiceType.natal, requires_question=False, positions=[],
         description="Персональный астрологический разбор по дате, времени и месту рождения.",
         sort_order=50),
]

NATAL_SYSTEM_PROMPT = (
    "Ты — профессиональный астролог. Интерпретируй ТОЛЬКО переданные рассчитанные "
    "данные натальной карты, ничего не пересчитывай. Отвечай по-русски. Структура: "
    "общий портрет, Солнце/Луна/Асцендент (если есть), ключевые аспекты, рекомендации. "
    "Если в данных есть предупреждения о точности — обязательно упомяни их. "
    "Не давай медицинских и финансовых советов."
)


async def main() -> None:
    async with SessionMaker() as session:
        if not await session.scalar(select(TarotCard).limit(1)):
            for c in build_deck():
                session.add(TarotCard(**c))
            print("Загружено 78 карт Таро")

        for spec in SERVICES:
            if await session.scalar(select(Service).where(Service.code == spec["code"])):
                continue
            service = Service(**spec)
            session.add(service)
            await session.flush()
            session.add(ServicePrompt(
                service_id=service.id,
                system_prompt=(NATAL_SYSTEM_PROMPT if service.type == ServiceType.natal
                               else BASE_SYSTEM_PROMPT),
                user_prompt_template=(
                    "Данные:\n{facts}\n\nВопрос пользователя: {question}\n\n"
                    "Дай развёрнутую интерпретацию каждой позиции, общий вывод и рекомендации."
                ),
            ))
            print(f"Создана услуга: {service.title}")
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
