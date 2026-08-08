"""Оплата Telegram Stars: pre_checkout, successful_payment, идемпотентность.

Защита от двойной выдачи:
- уникальное ограничение на telegram_payment_charge_id (payments);
- уникальное ограничение на order_id (generation_jobs);
- проверка и смена статуса заказа в одной транзакции.
"""
from aiogram import Bot, F, Router
from aiogram.types import Message, PreCheckoutQuery
from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import GenerationJob, Order, OrderStatus, Payment, User
from app.services.errors import log_error
from app.services.texts import get_setting

router = Router()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery, session: AsyncSession):
    try:
        order_id = int(query.invoice_payload.split(":")[1])
    except (IndexError, ValueError):
        await query.answer(ok=False, error_message="Некорректный заказ.")
        return
    order = await session.get(Order, order_id)
    if not order or order.status not in (OrderStatus.created, OrderStatus.invoiced):
        await query.answer(ok=False, error_message="Заказ не найден или уже оплачен.")
        return
    if order.final_price_stars != query.total_amount:
        await query.answer(ok=False, error_message="Сумма заказа изменилась, создайте заказ заново.")
        return
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message, session: AsyncSession,
                             db_user: User, bot: Bot):
    sp = message.successful_payment
    order_id = int(sp.invoice_payload.split(":")[1])

    # Одна транзакция: платёж (уникальный charge_id) + статус заказа + задание (уникальный order_id)
    order = await session.get(Order, order_id, with_for_update=True)
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

    await message.answer(await get_setting(session, "generation_in_progress"))

    try:
        redis = await create_pool(RedisSettings(
            host=get_settings().redis_host, port=get_settings().redis_port))
        await redis.enqueue_job("generate_result", order.id, _job_id=f"order-{order.id}")
        await redis.close()
    except Exception as e:
        await log_error(session, "queue", e, order_id=order.id, user_id=db_user.id)
        await session.commit()
