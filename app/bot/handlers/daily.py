"""Бесплатная карта дня: 1 карта в сутки (UTC+3), повторный запрос — та же карта."""
from aiogram import Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import budget, openai_client
from app.db.models import AIRequest, User
from app.services.daily import DailyDeckUnavailable, get_or_create_daily_card
from app.services.errors import log_error
from app.services.formatting import markdown_to_telegram_html
from app.services.texts import get_setting, get_text

router = Router()


async def is_daily_button(message: Message, session: AsyncSession) -> bool:
    return message.text == await get_setting(session, "btn_daily")


@router.message(is_daily_button)
async def daily_card(message: Message, session: AsyncSession, db_user: User):
    try:
        card, created = await get_or_create_daily_card(session, db_user.id)
    except DailyDeckUnavailable as exc:
        await log_error(session, "daily_card", exc, user_id=db_user.id)
        await session.commit()
        await message.answer(await get_text(session, "daily_unavailable"))
        return

    reversed_mark = ""
    if card.is_reversed:
        reversed_mark = " " + await get_text(session, "daily_reversed_mark")
    header = await get_text(session, "daily_header",
                            card=card.card.name_ru, reversed=reversed_mark)

    if not created and card.text:
        note = await get_text(session, "daily_repeat_note")
        await message.answer(f"{header}\n\n{card.text}\n\n{note}")
        return

    text = ""
    if (await get_setting(session, "daily_ai_enabled")) == "true":
        b = await budget.check_budget(session)
        if b["allowed"]:
            try:
                position = "перевёрнутом" if card.is_reversed else "прямом"
                result = await openai_client.generate(
                    system_prompt=await get_setting(session, "daily_ai_prompt"),
                    user_prompt=f"Карта дня: {card.card.name_ru} в {position} положении.",
                    max_output_tokens=512,
                )
                text = markdown_to_telegram_html(result["text"])
                session.add(AIRequest(
                    user_id=db_user.id, model=result["model"],
                    input_tokens=result["input_tokens"], output_tokens=result["output_tokens"],
                    cost_usd=budget.estimate_cost(result["model"], result["input_tokens"],
                                                  result["output_tokens"]),
                    status="ok", is_free_service=True,
                ))
            except openai_client.AIError as e:
                await log_error(session, "daily_card", e, user_id=db_user.id)

    if not text:
        meaning = (card.card.reversed_meaning if card.is_reversed
                   else card.card.upright_meaning) or await get_text(session, "daily_fallback")
        text = meaning

    card.text = text
    await session.commit()
    await message.answer(f"{header}\n\n{text}")
