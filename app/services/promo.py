"""Проверка и применение промокодов. Итоговая цена — целое число Stars, минимум 1."""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PromoActivation, PromoCode
from app.services.texts import get_text


async def validate_promo(
    session: AsyncSession, code: str, user_id: int, service_id: int, price_stars: int
) -> tuple[PromoCode | None, int, str | None]:
    """Возвращает (promo, final_price, error_message). Тексты ошибок — promo_err_* в админке."""
    promo = await session.scalar(
        select(PromoCode).where(func.lower(PromoCode.code) == code.strip().lower())
    )
    if not promo or not promo.is_active:
        return None, price_stars, await get_text(session, "promo_err_not_found")

    now = datetime.now(timezone.utc)
    if promo.starts_at and now < promo.starts_at:
        return None, price_stars, await get_text(session, "promo_err_not_started")
    if promo.ends_at and now > promo.ends_at:
        return None, price_stars, await get_text(session, "promo_err_expired")
    if promo.service_ids and service_id not in promo.service_ids:
        return None, price_stars, await get_text(session, "promo_err_wrong_service")
    if price_stars < promo.min_order_stars:
        return None, price_stars, await get_text(session, "promo_err_min_sum",
                                                 min=promo.min_order_stars)

    total = await session.scalar(
        select(func.count()).select_from(PromoActivation)
        .where(PromoActivation.promo_code_id == promo.id)
    )
    if promo.max_activations and total >= promo.max_activations:
        return None, price_stars, await get_text(session, "promo_err_limit")

    user_count = await session.scalar(
        select(func.count()).select_from(PromoActivation)
        .where(PromoActivation.promo_code_id == promo.id, PromoActivation.user_id == user_id)
    )
    if user_count >= promo.per_user_limit:
        return None, price_stars, await get_text(session, "promo_err_used")

    if promo.discount_percent:
        final = price_stars - price_stars * promo.discount_percent // 100
    elif promo.discount_stars:
        final = price_stars - promo.discount_stars
    else:
        final = price_stars
    return promo, max(1, int(final)), None
