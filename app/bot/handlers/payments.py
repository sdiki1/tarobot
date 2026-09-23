"""Оплата Telegram Stars: pre_checkout, successful_payment, идемпотентность.

Защита от двойной выдачи:
- уникальное ограничение на telegram_payment_charge_id (payments);
- уникальное ограничение на order_id (generation_jobs);
- проверка и смена статуса заказа в одной транзакции.
"""
from uuid import uuid4

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery
from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload

from app.config import get_settings
from app.db.models import GenerationJob, Order, OrderStatus, Payment, User
from app.services.errors import log_error
from app.services.texts import get_text

router = Router()


async def _get_order_for_update(session: AsyncSession, order_id: int) -> Order | None:
    """Загружает и блокирует только orders, без eager JOIN к services."""
    return await session.scalar(
        select(Order)
        .where(Order.id == order_id)
        .options(lazyload(Order.service))
        .with_for_update()
    )


async def _enqueue_generation(session: AsyncSession, order: Order, user_id: int) -> None:
    """Ставит оплаченную услугу в общую очередь генерации."""
    try:
        settings = get_settings()
        redis = await create_pool(RedisSettings(
            host=settings.redis_host, port=settings.redis_port))
        await redis.enqueue_job("generate_result", order.id, _job_id=f"order-{order.id}")
        await redis.close()
    except Exception as exc:
        await log_error(session, "queue", exc, order_id=order.id, user_id=user_id)
        await session.commit()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery, session: AsyncSession):
    try:
        order_id = int(query.invoice_payload.split(":")[1])
    except (IndexError, ValueError):
        await query.answer(ok=False,
                           error_message=await get_text(session, "checkout_err_invalid"))
        return
    order = await session.get(Order, order_id)
    if not order or order.status not in (OrderStatus.created, OrderStatus.invoiced):
        await query.answer(ok=False, error_message=await get_text(session, "checkout_err_paid"))
        return
    if order.final_price_stars != query.total_amount:
        await query.answer(ok=False,
                           error_message=await get_text(session, "checkout_err_amount"))
        return
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message, session: AsyncSession,
                             db_user: User, bot: Bot):
    sp = message.successful_payment
    order_id = int(sp.invoice_payload.split(":")[1])

    # Одна транзакция: платёж (уникальный charge_id) + статус заказа + задание (уникальный order_id)
    order = await _get_order_for_update(session, order_id)
    if order is None:
        await log_error(session, "payments", message=f"Оплата несуществующего заказа {order_id}",
                        user_id=db_user.id)
        await session.commit()
        return

    session.add(Payment(
        order_id=order.id, user_id=db_user.id,
        amount_stars=sp.total_amount, currency=sp.currency,
        telegram_payment_charge_id=sp.telegram_payment_charge_id,
        invoice_payload=sp.invoice_payload,
    ))
    order.status = OrderStatus.paid
    session.add(GenerationJob(order_id=order.id))
    try:
        await session.commit()
    except IntegrityError:
        # Повторное уведомление о той же оплате — ничего не создаём и не выдаём повторно.
        await session.rollback()
        return

    await message.answer(await get_text(session, "generation_in_progress"))

    await _enqueue_generation(session, order, db_user.id)


@router.callback_query(F.data.startswith("testpay:"))
async def test_payment(callback: CallbackQuery, session: AsyncSession, db_user: User):
    """Имитирует успешную оплату только для администраторов в тестовом режиме."""
    settings = get_settings()
    if not settings.test_payment_enabled or db_user.id not in settings.admin_ids:
        await callback.answer("Тестовая оплата недоступна.", show_alert=True)
        return

    try:
        order_id = int(callback.data.split(":", 1)[1])
    except (AttributeError, IndexError, ValueError):
        await callback.answer("Некорректный заказ.", show_alert=True)
        return

    order = await _get_order_for_update(session, order_id)
    if (
        order is None
        or order.user_id != db_user.id
        or order.status not in (OrderStatus.created, OrderStatus.invoiced)
    ):
        await callback.answer("Заказ не найден или уже оплачен.", show_alert=True)
        return

    session.add(Payment(
        order_id=order.id,
        user_id=db_user.id,
        amount_stars=order.final_price_stars,
        currency="XTR",
        telegram_payment_charge_id=f"test:{uuid4()}",
        invoice_payload=f"test:{order.id}",
        status="test",
    ))
    order.status = OrderStatus.paid
    session.add(GenerationJob(order_id=order.id))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        await callback.answer("Этот заказ уже обрабатывается.", show_alert=True)
        return

    await callback.answer("Тестовая оплата принята.")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "🧪 Тестовая оплата — Stars не списаны.\n\n"
        + await get_text(session, "generation_in_progress")
    )
    await _enqueue_generation(session, order, db_user.id)
