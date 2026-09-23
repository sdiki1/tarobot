"""Команды /start, /help, /terms, /privacy, /pd_consent, /paysupport, /unsubscribe,
/delete_my_data."""
import html
from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import consent_kb, main_menu
from app.bot.states import DeleteData
from app.db.models import (
    BirthProfile, DailyCard, Order, Result, User, UserConsent,
)
from app.services.texts import (
    DOCUMENTS, get_setting, get_text, render_consent_text, render_document, set_setting,
)

router = Router()

WELCOME_PHOTO = Path(__file__).resolve().parents[2] / "assets" / "welcome.jpeg"
PHOTO_CACHE_KEY = "welcome_photo_cache"  # "<размер>:<mtime>|<file_id>"
CAPTION_LIMIT = 1024


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


def _photo_signature() -> str | None:
    try:
        st = WELCOME_PHOTO.stat()
    except OSError:
        return None
    return f"{st.st_size}:{int(st.st_mtime)}"


async def send_welcome(message: Message, session: AsyncSession, text: str, reply_markup) -> None:
    """Приветствие с картинкой. file_id кешируется в settings до замены файла картинки."""
    signature = _photo_signature()
    if signature is None or len(text) > CAPTION_LIMIT:
        if signature is not None:
            await message.answer_photo(FSInputFile(WELCOME_PHOTO))
        await message.answer(text, reply_markup=reply_markup)
        return

    cached = await get_setting(session, PHOTO_CACHE_KEY)
    cached_sig, _, file_id = cached.partition("|")
    if file_id and cached_sig == signature:
        try:
            await message.answer_photo(file_id, caption=text, reply_markup=reply_markup)
            return
        except TelegramBadRequest:
            pass  # file_id устарел (например, сменился токен бота) — загружаем заново
    sent = await message.answer_photo(FSInputFile(WELCOME_PHOTO), caption=text,
                                      reply_markup=reply_markup)
    if sent.photo:
        await set_setting(session, PHOTO_CACHE_KEY, f"{signature}|{sent.photo[-1].file_id}")
        await session.commit()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, session: AsyncSession, db_user: User):
    await state.set_state(None)  # выходим из незавершённого ввода, данные заказа сохраняем
    welcome = await get_setting(session, "welcome_text")
    if await _has_consent(session, db_user.id):
        await send_welcome(message, session, welcome, await main_menu(session))
        return
    consent = await render_consent_text(session)
    await send_welcome(message, session, f"{welcome}\n\n{consent}", await consent_kb(session))


@router.callback_query(F.data == "consent:accept")
async def consent_accept(cb: CallbackQuery, session: AsyncSession, db_user: User):
    if not await _has_consent(session, db_user.id):
        version = await get_setting(session, "docs_version")
        for doc in DOCUMENTS:
            session.add(UserConsent(user_id=db_user.id, document=doc, version=version))
        await session.commit()
    await cb.answer()
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    await cb.message.answer(await get_text(session, "main_menu_text"),
                            reply_markup=await main_menu(session))


@router.message(Command("help"))
async def cmd_help(message: Message, session: AsyncSession):
    await message.answer(await get_text(session, "help_text"),
                         reply_markup=await main_menu(session))


@router.message(Command("terms"))
async def cmd_terms(message: Message, session: AsyncSession):
    await message.answer(await render_document(session, "terms"))


@router.message(Command("privacy"))
async def cmd_privacy(message: Message, session: AsyncSession):
    await message.answer(await render_document(session, "privacy"))


@router.message(Command("pd_consent"))
async def cmd_pd_consent(message: Message, session: AsyncSession):
    await message.answer(await render_document(session, "pd_consent"))


@router.message(Command("paysupport"))
async def cmd_paysupport(message: Message, session: AsyncSession):
    await message.answer(await get_setting(session, "paysupport_text"))


@router.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message, session: AsyncSession, db_user: User):
    db_user.subscribed = not db_user.subscribed
    await session.commit()
    key = "subscribe_done" if db_user.subscribed else "unsubscribe_done"
    await message.answer(await get_text(session, key))


@router.callback_query(F.data == "unsub:broadcast")
async def unsub_from_broadcast(cb: CallbackQuery, session: AsyncSession, db_user: User):
    db_user.subscribed = False
    await session.commit()
    await cb.answer(await get_text(session, "alert_unsubscribed"), show_alert=True)


@router.message(Command("delete_my_data"))
async def cmd_delete_data(message: Message, state: FSMContext, session: AsyncSession):
    await state.set_state(DeleteData.confirm)
    word = await get_setting(session, "delete_confirm_word")
    await message.answer(await get_text(session, "delete_prompt", word=html.escape(word)))


@router.message(DeleteData.confirm)
async def delete_data_confirm(message: Message, state: FSMContext,
                              session: AsyncSession, db_user: User):
    await state.clear()
    word = await get_setting(session, "delete_confirm_word")
    if (message.text or "").strip().upper() != word.strip().upper():
        await message.answer(await get_text(session, "delete_cancelled"))
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
    await message.answer(await get_text(session, "delete_done"))
