"""Контроль расходов на ИИ: дневной и месячный бюджеты, уведомления на 80% и 100%."""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import AIRequest

# Ориентировочные цены за 1M токенов (USD); уточняются в настройках при смене модели.
PRICES = {
    "gpt-5.6-luna": {"input": 0.20, "output": 1.20},
    "gpt-5.4-nano": {"input": 0.20, "output": 1.25},
    "default": {"input": 0.30, "output": 2.50},
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    p = PRICES.get(model, PRICES["default"])
    return input_tokens / 1e6 * p["input"] + output_tokens / 1e6 * p["output"]


async def spent_usd(session: AsyncSession, since: datetime) -> float:
    total = await session.scalar(
        select(func.coalesce(func.sum(AIRequest.cost_usd), 0)).where(AIRequest.created_at >= since)
    )
    return float(total or 0)


async def check_budget(session: AsyncSession) -> dict:
    """Возвращает {'allowed': bool, 'use_fallback': bool, 'warn': str | None}."""
    s = get_settings()
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = day_start.replace(day=1)

    day = await spent_usd(session, day_start)
    month = await spent_usd(session, month_start)

    warn = None
    for spent, limit, name in ((day, s.ai_daily_budget_usd, "дневного"),
                               (month, s.ai_monthly_budget_usd, "месячного")):
        if limit <= 0:
            continue
        if spent >= limit:
            if s.ai_budget_action == "fallback":
                return {"allowed": True, "use_fallback": True,
                        "warn": f"Достигнуто 100% {name} лимита ИИ (${spent:.2f}). Включена резервная модель."}
            return {"allowed": False, "use_fallback": False,
                    "warn": f"Достигнуто 100% {name} лимита ИИ (${spent:.2f}). Генерации заблокированы."}
        if spent >= 0.8 * limit:
            warn = f"Достигнуто 80% {name} лимита ИИ: ${spent:.2f} из ${limit:.2f}."
    return {"allowed": True, "use_fallback": False, "warn": warn}
