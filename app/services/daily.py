"""Бесплатная карта дня: одна карта в сутки по UTC+3, повторный запрос возвращает ту же."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DailyCard, TarotCard
from app.services.texts import get_setting
from app.tarot.draw import DECK_SIZE, draw_cards

TZ_MSK = timezone(timedelta(hours=3))


class DailyDeckUnavailable(RuntimeError):
    """Колода в БД ещё не заполнена или заполнена не полностью."""


def today_msk():
    return datetime.now(TZ_MSK).date()


async def get_or_create_daily_card(session: AsyncSession, user_id: int) -> tuple[DailyCard, bool]:
    """Возвращает (карта, created). Уникальный индекс (user_id, day) исключает
    выдачу второй бесплатной карты при гонке одновременных запросов."""
    day = today_msk()
    existing = await session.scalar(
        select(DailyCard).where(DailyCard.user_id == user_id, DailyCard.day == day)
    )
    if existing and existing.card is not None:
        return existing, False
    if existing:
        raise DailyDeckUnavailable(
            f"Для карты дня {existing.id} отсутствует карта Таро {existing.card_id}"
        )

    cards_count = await session.scalar(select(func.count()).select_from(TarotCard))
    if cards_count != DECK_SIZE:
        raise DailyDeckUnavailable(
            f"Ожидалось {DECK_SIZE} карт Таро, найдено {cards_count or 0}"
        )

    allow_reversed = (await get_setting(session, "daily_reversed_enabled")) == "true"
    drawn = draw_cards(1, allow_reversed=allow_reversed)[0]
    card = DailyCard(user_id=user_id, day=day,
                     card_id=drawn["card_id"], is_reversed=drawn["is_reversed"])
    session.add(card)
    try:
        await session.commit()
    except IntegrityError:
        # Параллельный запрос успел первым — отдаём его карту.
        await session.rollback()
        existing = await session.scalar(
            select(DailyCard).where(DailyCard.user_id == user_id, DailyCard.day == day)
        )
        if existing is not None:
            return existing, False
        # Это было другое нарушение целостности, скрывать его как гонку нельзя.
        raise
    await session.refresh(card, ["card"])
    return card, True
