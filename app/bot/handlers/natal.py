"""Натальная карта: выбор услуги, сбор данных рождения, геокодинг, выбор точности времени, оплата."""
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.tarot import send_invoice
from app.bot.keyboards import promo_kb
from app.bot.states import NatalOrder
from app.config import get_settings
from app.db.models import BirthProfile, Order, Service, ServiceType, User
from app.natal.calc import HAS_SWE
from app.natal.geocode import geocode
from app.services.errors import log_error
from app.services.texts import get_setting

router = Router()

UNAVAILABLE_TEXT = "Раздел «Натальная карта» временно недоступен. Загляните позже 🙏"

# Маркеры в Service.required_fields для услуг типа natal:
#   partner  — собрать данные рождения второго человека (совместимость)
#   transits — рассчитать транзиты на 12 месяцев вперёд (прогноз); используется воркером
PARTNER_FIELD = "partner"


async def is_natal_button(message: Message, session: AsyncSession) -> bool:
    return message.text == await get_setting(session, "btn_natal")


def _active_natal(service: Service | None) -> bool:
    return bool(service and service.type == ServiceType.natal
                and service.is_active and not service.is_archived)


@router.message(is_natal_button)
async def natal_menu(message: Message, state: FSMContext, session: AsyncSession):
    """Раздел «Натальная карта»: список услуг кнопками."""
    await state.set_state(None)
    if not HAS_SWE:  # без модуля расчёта заказ завершится ошибкой — оплату не принимаем
        await message.answer(UNAVAILABLE_TEXT)
        return
    services = (await session.scalars(
        select(Service).where(Service.type == ServiceType.natal,
                              Service.is_active.is_(True), Service.is_archived.is_(False))
        .order_by(Service.sort_order, Service.id)
    )).all()
    if not services:
        await message.answer("Услуга «Натальная карта» временно недоступна.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=s.title[:64], callback_data=f"natal:{s.id}")]
        for s in services
    ])
    await message.answer(await get_setting(session, "natal_menu_text"), reply_markup=kb)


def _card_text(service: Service) -> str:
    """Описание со своим заголовком (<b>…</b> в начале) выводится без названия услуги."""
    description = service.description.strip()
    if not description.startswith("<b>"):
        description = f"<b>{service.title}</b>\n\n{description}"
    return f"{description}\n\nСтоимость: {service.price_stars} ⭐"


@router.callback_query(F.data.startswith("natal:"))
async def natal_service_card(cb: CallbackQuery, session: AsyncSession):
    """Описание услуги и кнопка «РАССЧИТАТЬ» (или своя кнопка услуги)."""
    service = await session.get(Service, int(cb.data.split(":")[1]))
    if not _active_natal(service):
        await cb.answer("Услуга недоступна", show_alert=True)
        return
    text = _card_text(service)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=(service.button_text
              or await get_setting(session, "btn_calculate") or "РАССЧИТАТЬ"),
        callback_data=f"natalgo:{service.id}",
    )]])
    await cb.answer()
    if service.image_file_id and len(text) <= 1024:
        await cb.message.answer_photo(service.image_file_id, caption=text, reply_markup=kb)
    else:
        await cb.message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("natalgo:"))
async def natal_start(cb: CallbackQuery, state: FSMContext,
                      session: AsyncSession, db_user: User):
    service = await session.get(Service, int(cb.data.split(":")[1]))
    if not _active_natal(service) or not HAS_SWE:
        await cb.answer("Услуга временно недоступна", show_alert=True)
        return

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

    needs_partner = PARTNER_FIELD in (service.required_fields or [])
    await state.set_state(NatalOrder.name)
    await state.update_data(service_id=service.id, needs_partner=needs_partner,
                            person=0, profile_ids=[], names=[], variants=None)
    await cb.answer()
    if needs_partner:
        await cb.message.answer(
            "Для расчёта нужны данные рождения двух человек.\n\n"
            "Сначала ваши данные. Введите ваше имя:"
        )
    else:
        await cb.message.answer("Введите имя или обозначение профиля:")


@router.message(NatalOrder.name)
async def natal_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()[:128]
    if not name:
        await message.answer("Введите имя текстом:")
        return
    await state.update_data(name=name)
    await state.set_state(NatalOrder.birth_date)
    await message.answer("Введите дату рождения (ДД.ММ.ГГГГ):")


@router.message(NatalOrder.birth_date)
async def natal_birth_date(message: Message, state: FSMContext):
    try:
        d = datetime.strptime((message.text or "").strip(), "%d.%m.%Y").date()
    except ValueError:
        await message.answer("Неверный формат. Пример: 21.03.1990")
        return
    if d > datetime.now().date() or d.year < 1800:
        await message.answer("Проверьте дату рождения. Пример: 21.03.1990")
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

    profile_ids = [*data.get("profile_ids", []), profile.id]
    names = [*data.get("names", []), data["name"]]

    if data.get("needs_partner") and data.get("person", 0) == 0:
        # Первый профиль сохранён — собираем данные второго человека
        await session.commit()
        await state.update_data(profile_ids=profile_ids, names=names, person=1,
                                variants=None, birth_time=None)
        await state.set_state(NatalOrder.name)
        await message.answer("Отлично! Теперь данные второго человека.\nВведите его имя:")
        return

    service = await session.get(Service, data["service_id"])
    input_data = {"birth_profile_id": profile_ids[0], "name": names[0]}
    if len(profile_ids) > 1:
        input_data.update(partner_birth_profile_id=profile_ids[1], partner_name=names[1])
    order = Order(
        user_id=db_user.id, service_id=service.id,
        input_data=input_data,
        price_stars=service.price_stars, final_price_stars=service.price_stars,
    )
    session.add(order)
    await session.commit()
    await state.set_state(None)
    await state.update_data(order_id=order.id, variants=None, profile_ids=[], names=[])
    await message.answer(
        f"Заказ №{order.id} создан. Сумма: {order.final_price_stars} ⭐",
        reply_markup=promo_kb(
            order.id,
            get_settings().test_payment_enabled and db_user.id in get_settings().admin_ids,
        ),
    )
