from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.texts import get_setting


async def main_menu(session: AsyncSession) -> ReplyKeyboardMarkup:
    b = {k: await get_setting(session, k) for k in (
        "btn_daily", "btn_tarot", "btn_natal", "btn_results", "btn_support",
    )}
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=b["btn_daily"])],
            [KeyboardButton(text=b["btn_tarot"]), KeyboardButton(text=b["btn_natal"])],
            [KeyboardButton(text=b["btn_results"]), KeyboardButton(text=b["btn_support"])],
        ],
        resize_keyboard=True,
    )


async def consent_kb(session: AsyncSession) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=await get_setting(session, "btn_start") or "НАЧАТЬ",
                             callback_data="consent:accept"),
    ]])


def promo_kb(order_id: int | None = None, test_payment: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🎟 Ввести промокод", callback_data="promo:enter")],
        [InlineKeyboardButton(text="💳 Перейти к оплате", callback_data="promo:skip")],
    ]
    if test_payment and order_id is not None:
        buttons.append([InlineKeyboardButton(
            text="🧪 Тестовая оплата",
            callback_data=f"testpay:{order_id}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
