"""Натальная карта: сбор данных рождения, геокодинг, выбор точности времени, оплата."""
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.tarot import send_invoice
from app.bot.keyboards import promo_kb
from app.bot.states import NatalOrder
from app.db.models import BirthProfile, Order, Service, ServiceType, User
from app.natal.geocode import geocode
from app.services.errors import log_error
from app.services.texts import get_setting

router = Router()


async def is_natal_button(message: Message, session: AsyncSession) -> bool:
    return message.text == await get_setting(session, "btn_natal")


@router.message(is_natal_button)
async def natal_start(message: Message, state: FSMContext, session: AsyncSession):
    service = await session.scalar(
        select(Service).where(Service.type == ServiceType.natal,
                              Service.is_active.is_(True), Service.is_archived.is_(False))
        .order_by(Service.sort_order)
    )
    if not service:
        await message.answer("Услуга «Натальная карта» временно недоступна.")
        return
    await state.set_state(NatalOrder.name)
    await state.update_data(service_id=service.id)
    await message.answer(
        f"✨ <b>{service.title}</b> — {service.price_stars} ⭐\n{service.description}\n\n"
        "Введите имя или обозначение профиля:"
    )


@router.message(NatalOrder.name)
async def natal_name(message: Message, state: FSMContext):
    await state.update_data(name=(message.text or "").strip()[:128])
    await state.set_state(NatalOrder.birth_date)
    await message.answer("Введите дату рождения (ДД.ММ.ГГГГ):")


@router.message(NatalOrder.birth_date)
async def natal_birth_date(message: Message, state: FSMContext):
    try:
        d = datetime.strptime((message.text or "").strip(), "%d.%m.%Y").date()
    except ValueError:
        await message.answer("Неверный формат. Пример: 21.03.1990")
        return
    await state.update_data(birth_date=d.isoformat())
    await state.set_state(NatalOrder.time_accuracy)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏱ Точное время до минуты", callback_data="acc:exact")],
        [InlineKeyboardButton(text="🕐 Известен примерный час", callback_data="acc:approx_hour")],
        [InlineKeyboardButton(text="❓ Время неизвестно", callback_data="acc:unknown")],
    ])
    await message.answer("Насколько точно известно время рождения?", reply_markup=kb)


@router.callback_query(NatalOrder.time_accuracy, F.data.startswith("acc:"))
async def natal_accuracy(cb: CallbackQuery, state: FSMContext):
    acc = cb.data.split(":")[1]
    await state.update_data(time_accuracy=acc)
    await cb.answer()
    if acc == "exact":
        await state.set_state(NatalOrder.birth_time)
        await cb.message.answer("Введите время рождения (ЧЧ:ММ):")
    elif acc == "approx_hour":
        await state.set_state(NatalOrder.birth_time)
        await cb.message.answer(
            "Введите примерный час рождения (например, 14):\n"
            "<i>Расчёт будет выполнен на середину часа; дома и Асцендент — с возможной "
            "погрешностью.</i>"
        )
    else:
        await state.update_data(birth_time=None)
        await state.set_state(NatalOrder.place)
        await cb.message.answer(
            "Введите населённый пункт рождения:\n"
            "<i>Без времени рождения Асцендент и дома не рассчитываются, разбор будет "
            "ограниченным.</i>"
        )


@router.message(NatalOrder.birth_time)
async def natal_time(message: Message, state: FSMContext):
    data = await state.get_data()
    raw = (message.text or "").strip()
    try:
        if data["time_accuracy"] == "exact":
            t = datetime.strptime(raw, "%H:%M")
            value = t.strftime("%H:%M")
        else:
            hour = int(raw.split(":")[0])
            if not 0 <= hour <= 23:
                raise ValueError
            value = f"{hour:02d}:00"
    except (ValueError, IndexError):
        await message.answer("Неверный формат. Пример: 14:30 (или просто 14 для часа).")
        return
    await state.update_data(birth_time=value)
    await state.set_state(NatalOrder.place)
    await message.answer("Введите населённый пункт рождения:")


@router.message(NatalOrder.place)
async def natal_place(message: Message, state: FSMContext,
                      session: AsyncSession, db_user: User):
    place = (message.text or "").strip()
    try:
        variants = await geocode(place)
    except Exception as e:
        await log_error(session, "geocoder", e, user_id=db_user.id)
        await session.commit()
        await message.answer("Сервис геокодинга временно недоступен, попробуйте позже.")
        return
    if not variants:
        await message.answer("Населённый пункт не найден. Уточните название:")
        return
    if len(variants) == 1:
        await _finish_place(message, state, session, db_user, variants[0])
        return
    await state.update_data(variants=variants)
    await state.set_state(NatalOrder.place_choice)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=v["name"][:60], callback_data=f"place:{i}")]
        for i, v in enumerate(variants)
    ])
    await message.answer("Найдено несколько вариантов, выберите нужный:", reply_markup=kb)


@router.callback_query(NatalOrder.place_choice, F.data.startswith("place:"))
async def natal_place_choice(cb: CallbackQuery, state: FSMContext,
                             session: AsyncSession, db_user: User):
    data = await state.get_data()
    variant = data["variants"][int(cb.data.split(":")[1])]
    await cb.answer()
    await _finish_place(cb.message, state, session, db_user, variant)


async def _finish_place(message: Message, state: FSMContext, session: AsyncSession,
                        db_user: User, variant: dict):
    data = await state.get_data()
    profile = BirthProfile(
        user_id=db_user.id,
        label=data["name"],
        birth_date=datetime.fromisoformat(data["birth_date"]).date(),
        birth_time=data.get("birth_time"),
        time_accuracy=data["time_accuracy"],
        place_name=variant["name"][:256],
        latitude=variant["lat"], longitude=variant["lon"],
        tz_id=variant["tz_id"],
    )
    session.add(profile)
    await session.flush()

    service = await session.get(Service, data["service_id"])
    order = Order(
        user_id=db_user.id, service_id=service.id,
        input_data={"birth_profile_id": profile.id, "name": data["name"]},
        price_stars=service.price_stars, final_price_stars=service.price_stars,
    )
    session.add(order)
    await session.commit()
    await state.set_state(None)
    await state.update_data(order_id=order.id, variants=None)
    await message.answer(
        f"Заказ №{order.id} создан. Сумма: {order.final_price_stars} ⭐",
        reply_markup=promo_kb(),
    )
