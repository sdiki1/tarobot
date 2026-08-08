"""«Мои результаты» и «Поддержка»: история заказов, повторное открытие результата."""
from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Order, OrderStatus, Result, User
from app.services.texts import get_setting

router = Router()

STATUS_RU = {
    "created": "создан", "invoiced": "ожидает оплаты", "paid": "оплачен, готовится",
    "completed": "готов", "failed": "ошибка", "refunded": "возврат", "cancelled": "отменён",
}


async def is_results_button(message: Message, session: AsyncSession) -> bool:
    return message.text == await get_setting(session, "btn_results")


async def is_support_button(message: Message, session: AsyncSession) -> bool:
    return message.text == await get_setting(session, "btn_support")


async def is_terms_button(message: Message, session: AsyncSession) -> bool:
    return message.text == await get_setting(session, "btn_terms")


async def is_privacy_button(message: Message, session: AsyncSession) -> bool:
    return message.text == await get_setting(session, "btn_privacy")


@router.message(is_results_button)
async def my_results(message: Message, session: AsyncSession, db_user: User):
    orders = (await session.scalars(
        select(Order).where(Order.user_id == db_user.id)
        .order_by(Order.created_at.desc()).limit(10)
    )).all()
    if not orders:
        await message.answer("У вас пока нет заказов.")
        return
    rows = []
    for o in orders:
        label = (f"№{o.id} · {o.service.title} · {o.final_price_stars}⭐ · "
                 f"{STATUS_RU.get(o.status.value, o.status.value)}")
        rows.append([InlineKeyboardButton(text=label[:64], callback_data=f"res:{o.id}")])
    await message.answer("📜 Последние заказы:",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("res:"))
async def open_result(cb: CallbackQuery, session: AsyncSession, db_user: User):
    order_id = int(cb.data.split(":")[1])
    order = await session.get(Order, order_id)
    if not order or order.user_id != db_user.id:
        await cb.answer("Заказ не найден", show_alert=True)
        return
    result = await session.scalar(select(Result).where(Result.order_id == order_id))
    await cb.answer()
    if result:
        for i in range(0, len(result.text), 4000):
            await cb.message.answer(result.text[i:i + 4000])
    else:
        await cb.message.answer(
            f"Заказ №{order.id}: {STATUS_RU.get(order.status.value, order.status.value)}. "
            "Результат пока не готов."
        )


@router.message(is_support_button)
async def support(message: Message, session: AsyncSession):
    await message.answer(await get_setting(session, "support_text"))


@router.message(is_terms_button)
async def terms_btn(message: Message, session: AsyncSession):
    await message.answer(await get_setting(session, "terms_text"))


@router.message(is_privacy_button)
async def privacy_btn(message: Message, session: AsyncSession):
    await message.answer(await get_setting(session, "privacy_text"))
