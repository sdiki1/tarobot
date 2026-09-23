"""Платные расклады Таро: каталог, сбор входных данных, промокод, счёт в Stars."""
import html
import re
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Message,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import promo_kb
from app.bot.states import TarotOrder
from app.config import get_settings
from app.db.models import Order, OrderStatus, Service, ServiceType, User
from app.services.promo import validate_promo
from app.services.texts import get_setting

router = Router()

FIELD_PROMPTS = {
    "question": "Сформулируйте ваш вопрос:",
    "name": "Введите ваше имя:",
    "birth_date": "Введите вашу дату рождения (ДД.ММ.ГГГГ):",
    "partner_name": "Введите имя другого человека:",
    "situation": "Опишите ситуацию:",
    "comment": "Дополнительные комментарии (или «-», если нет):",
}


async def is_tarot_button(message: Message, session: AsyncSession) -> bool:
    return message.text == await get_setting(session, "btn_tarot")


@router.message(is_tarot_button)
async def catalog(message: Message, session: AsyncSession):
    services = (await session.scalars(
        select(Service)
        .where(Service.type == ServiceType.tarot, Service.is_active.is_(True),
               Service.is_archived.is_(False))
        .order_by(Service.sort_order)
    )).all()
    if not services:
        await message.answer("Каталог пока пуст.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{s.title} — {s.price_stars} ⭐",
                              callback_data=f"svc:{s.id}")]
        for s in services
    ])
    await message.answer("🔮 Выберите расклад:", reply_markup=kb)


@router.callback_query(F.data.startswith("svc:"))
async def service_selected(cb: CallbackQuery, state: FSMContext,
                           session: AsyncSession, db_user: User):
    service = await session.get(Service, int(cb.data.split(":")[1]))
    if not service or not service.is_active or service.is_archived:
        await cb.answer("Услуга недоступна", show_alert=True)
        return

    # Лимит запросов на пользователя в сутки
    day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    count = await session.scalar(
        select(func.count()).select_from(Order).where(
            Order.user_id == db_user.id, Order.service_id == service.id,
            Order.created_at >= day_ago,
        )
    )
    if service.per_user_daily_limit and count >= service.per_user_daily_limit:
        await cb.answer("Достигнут дневной лимит по этой услуге. Попробуйте завтра.",
                        show_alert=True)
        return

    fields = list(service.required_fields or [])
    if service.requires_question and "question" not in fields:
        fields.insert(0, "question")

    await state.set_state(TarotOrder.collecting)
    await state.update_data(service_id=service.id, fields=fields, field_idx=0, inputs={})
    text = f"<b>{service.title}</b>\n{service.description}\nСтоимость: {service.price_stars} ⭐"
    if service.image_file_id:
        await cb.message.answer_photo(service.image_file_id, caption=text)
    else:
        await cb.message.answer(text)
    await cb.answer()
    await _ask_next_field(cb.message, state, session, db_user)


async def _ask_next_field(message: Message, state: FSMContext,
                          session: AsyncSession, db_user: User):
    data = await state.get_data()
    fields, idx = data["fields"], data["field_idx"]
    if idx < len(fields):
        await message.answer(FIELD_PROMPTS.get(fields[idx], f"Введите: {fields[idx]}"))
        return
    # Все поля собраны — создаём заказ
    service = await session.get(Service, data["service_id"])
    order = Order(
        user_id=db_user.id, service_id=service.id,
        input_data=data["inputs"],
        price_stars=service.price_stars, final_price_stars=service.price_stars,
    )
    session.add(order)
    await session.commit()
    await state.set_state(None)
    await state.update_data(order_id=order.id)
    await message.answer(
        f"Заказ №{order.id} создан. Сумма: {order.final_price_stars} ⭐",
        reply_markup=promo_kb(
            order.id,
            get_settings().test_payment_enabled and db_user.id in get_settings().admin_ids,
        ),
    )


@router.message(TarotOrder.collecting)
async def collect_field(message: Message, state: FSMContext,
                        session: AsyncSession, db_user: User):
    data = await state.get_data()
    fields, idx, inputs = data["fields"], data["field_idx"], data["inputs"]
    inputs[fields[idx]] = (message.text or "").strip()[:2000]
    await state.update_data(inputs=inputs, field_idx=idx + 1)
    await _ask_next_field(message, state, session, db_user)


@router.callback_query(F.data == "promo:enter")
async def promo_enter(cb: CallbackQuery, state: FSMContext):
    await state.set_state(TarotOrder.promo)
    await cb.message.answer("Введите промокод:")
    await cb.answer()


@router.message(TarotOrder.promo)
async def promo_apply(message: Message, state: FSMContext,
                      session: AsyncSession, db_user: User):
    data = await state.get_data()
    order = await session.get(Order, data["order_id"])
    promo, final, err = await validate_promo(
        session, message.text or "", db_user.id, order.service_id, order.price_stars
    )
    await state.set_state(None)
    if err:
        await message.answer(
            f"❌ {err}",
            reply_markup=promo_kb(
                order.id,
                get_settings().test_payment_enabled and db_user.id in get_settings().admin_ids,
            ),
        )
        return
    order.promo_code_id = promo.id
    order.final_price_stars = final
    await session.commit()
    await message.answer(f"✅ Промокод применён. Итог: {final} ⭐")
    await send_invoice(message, session, order)


@router.callback_query(F.data == "promo:skip")
async def promo_skip(cb: CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    order = await session.get(Order, data.get("order_id"))
    if not order:
        await cb.answer("Заказ не найден", show_alert=True)
        return
    await cb.answer()
    await send_invoice(cb.message, session, order)


def invoice_title(title: str, limit: int = 32) -> str:
    """Заголовок счёта: без ведущих эмодзи, не длиннее 32 символов, обрезка по словам."""
    title = title.strip()
    while title and not title[0].isalnum():
        title = title[1:].lstrip()
    if len(title) <= limit:
        return title or "Услуга"
    cut = title[:limit - 1].rsplit(" ", 1)[0]
    return cut.rstrip(" ,.;:—-") + "…"


def invoice_description(service: Service, limit: int = 240) -> str:
    """Описание счёта: без HTML-разметки, обрезка по словам. Лимит Telegram — 255 символов,
    запас — на эмодзи, которые считаются за два символа."""
    text = html.unescape(re.sub(r"<[^>]+>", "", service.description or "")).strip()
    text = text or service.title
    if len(text) <= limit:
        return text
    cut = text[:limit - 1].rsplit(" ", 1)[0]
    return cut.rstrip(" ,.;:—-\n") + "…"


async def send_invoice(message: Message, session: AsyncSession, order: Order):
    """Счёт в Telegram Stars (валюта XTR, provider_token пустой)."""
    order.status = OrderStatus.invoiced
    await session.commit()
    await message.answer_invoice(
        title=invoice_title(order.service.title),
        description=invoice_description(order.service),
        payload=f"order:{order.id}",
        currency="XTR",
        prices=[LabeledPrice(label=invoice_title(order.service.title),
                             amount=order.final_price_stars)],
    )
