"""Бесплатная карта дня: одна карта в сутки по UTC+3, повторный запрос возвращает ту же."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DailyCard
from app.services.texts import get_setting
from app.tarot.draw import draw_cards

TZ_MSK = timezone(timedelta(hours=3))


def today_msk():
    return datetime.now(TZ_MSK).date()


async def get_or_create_daily_card(session: AsyncSession, user_id: int) -> tuple[DailyCard, bool]:
    """Возвращает (карта, created). Уникальный индекс (user_id, day) исключает
    выдачу второй бесплатной карты при гонке одновременных запросов."""
    day = today_msk()
    existing = await session.scalar(
        select(DailyCard).where(DailyCard.user_id == user_id, DailyCard.day == day)
    )
    if existing:
        return existing, False

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
        return existing, False
    await session.refresh(card, ["card"])
    return card, True
