"""Команды /start, /help, /terms, /privacy, /paysupport, /unsubscribe, /delete_my_data."""
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import consent_kb, main_menu
from app.bot.states import DeleteData
from app.db.models import (
    BirthProfile, DailyCard, Order, Result, User, UserConsent,
)
from app.services.texts import get_setting

router = Router()


async def _has_consent(session: AsyncSession, user_id: int) -> bool:
    version = await get_setting(session, "docs_version")
    row = await session.scalar(
        select(UserConsent).where(
            UserConsent.user_id == user_id,
            UserConsent.document == "terms",
            UserConsent.version == version,
        )
    )
    return row is not None


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, db_user: User):
    if await _has_consent(session, db_user.id):
        await message.answer(
            await get_setting(session, "welcome_text"),
            reply_markup=await main_menu(session),
        )
        return
    await message.answer(await get_setting(session, "welcome_text"))
    await message.answer(await get_setting(session, "consent_text"), reply_markup=consent_kb())


@router.callback_query(F.data == "consent:accept")
async def consent_accept(cb: CallbackQuery, session: AsyncSession, db_user: User):
    version = await get_setting(session, "docs_version")
    for doc in ("terms", "privacy"):
        session.add(UserConsent(user_id=db_user.id, document=doc, version=version))
    await session.commit()
    await cb.message.answer("Спасибо! Главное меню:", reply_markup=await main_menu(session))
    await cb.answer()


@router.message(Command("help"))
async def cmd_help(message: Message, session: AsyncSession):
    await message.answer(
        "Доступные команды:\n"
        "/start — главное меню\n/terms — условия использования\n"
        "/privacy — политика конфиденциальности\n/paysupport — поддержка по оплате\n"
        "/unsubscribe — отказ от рассылок\n/delete_my_data — удаление данных",
        reply_markup=await main_menu(session),
    )


@router.message(Command("terms"))
async def cmd_terms(message: Message, session: AsyncSession):
    await message.answer(await get_setting(session, "terms_text"))


@router.message(Command("privacy"))
async def cmd_privacy(message: Message, session: AsyncSession):
    await message.answer(await get_setting(session, "privacy_text"))


@router.message(Command("paysupport"))
async def cmd_paysupport(message: Message, session: AsyncSession):
    await message.answer(await get_setting(session, "paysupport_text"))


@router.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message, session: AsyncSession, db_user: User):
    db_user.subscribed = not db_user.subscribed
    await session.commit()
    if db_user.subscribed:
        await message.answer("Вы снова подписаны на рассылки. Отписаться: /unsubscribe")
    else:
        await message.answer(
            "Вы отписаны от рекламных рассылок. Сообщения по вашим заказам "
            "будут приходить по-прежнему. Подписаться снова: /unsubscribe"
        )


@router.callback_query(F.data == "unsub:broadcast")
async def unsub_from_broadcast(cb: CallbackQuery, session: AsyncSession, db_user: User):
    db_user.subscribed = False
    await session.commit()
    await cb.answer("Вы отписаны от рассылок", show_alert=True)


@router.message(Command("delete_my_data"))
async def cmd_delete_data(message: Message, state: FSMContext):
    await state.set_state(DeleteData.confirm)
    await message.answer(
        "Вы запросили удаление персональных данных: профиль, вопросы, данные рождения, "
        "сохранённые результаты и настройки рассылок будут удалены. Платёжные сведения "
        "сохраняются в минимально необходимом объёме для возвратов и учёта.\n\n"
        "Для подтверждения отправьте слово: УДАЛИТЬ"
    )


@router.message(DeleteData.confirm)
async def delete_data_confirm(message: Message, state: FSMContext,
                              session: AsyncSession, db_user: User):
    await state.clear()
    if (message.text or "").strip().upper() != "УДАЛИТЬ":
        await message.answer("Удаление отменено.")
        return
    await session.execute(delete(BirthProfile).where(BirthProfile.user_id == db_user.id))
    await session.execute(delete(Result).where(Result.user_id == db_user.id))
    await session.execute(delete(DailyCard).where(DailyCard.user_id == db_user.id))
    await session.execute(
        update(Order).where(Order.user_id == db_user.id).values(input_data={})
    )
    db_user.username = None
    db_user.first_name = None
    db_user.subscribed = False
    db_user.deleted_at = func.now()
    await session.commit()
    await message.answer("Ваши персональные данные удалены/обезличены.")
