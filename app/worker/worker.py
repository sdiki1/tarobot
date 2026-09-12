"""Очередь фоновых заданий (arq + Redis).

generate_result: выбор карт / расчёт натальной карты -> промпт -> OpenAI -> результат.
Повторные попытки с увеличивающейся задержкой; после исчерпания — уведомление админа.
"""
import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from arq import Retry
from arq.connections import RedisSettings
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import budget, openai_client
from app.bot.notify import notify_admins
from app.config import get_settings
from app.db.models import (
    AIRequest, BirthProfile, GenerationJob, JobStatus, NatalCalculation, Order,
    OrderStatus, Result, ServicePrompt, ServiceType, TarotDraw, User,
)
from app.db.session import SessionMaker
from app.natal.calc import calculate_natal
from app.services.errors import log_error
from app.services.texts import get_setting
from app.tarot.draw import draw_cards

log = logging.getLogger(__name__)

RETRY_DELAYS = [30, 120, 600]  # растущая задержка между попытками


async def _prepare_tarot(session: AsyncSession, order: Order) -> str:
    """Выбирает карты (если ещё не выбраны) и возвращает их текстовое описание."""
    draws = (await session.scalars(
        select(TarotDraw).where(TarotDraw.order_id == order.id)
        .order_by(TarotDraw.position_index)
    )).all()
    if not draws:
        service = order.service
        positions = service.positions or [f"Позиция {i+1}" for i in range(service.cards_count)]
        drawn = draw_cards(service.cards_count,
                           allow_reversed=service.allow_reversed,
                           allow_duplicates=service.allow_duplicates)
        for i, d in enumerate(drawn):
            session.add(TarotDraw(
                order_id=order.id, card_id=d["card_id"], position_index=i,
                position_name=positions[i] if i < len(positions) else f"Позиция {i+1}",
                is_reversed=d["is_reversed"],
            ))
        await session.commit()
        draws = (await session.scalars(
            select(TarotDraw).where(TarotDraw.order_id == order.id)
            .order_by(TarotDraw.position_index)
        )).all()
    lines = []
    for d in draws:
        pos = f" ({'перевёрнутая' if d.is_reversed else 'прямая'})"
        lines.append(f"{d.position_index + 1}. {d.position_name}: {d.card.name_ru}{pos}")
    return "\n".join(lines)


async def _prepare_natal(session: AsyncSession, order: Order) -> str:
    profile = await session.get(BirthProfile, order.input_data["birth_profile_id"])
    calc = await session.scalar(
        select(NatalCalculation).where(NatalCalculation.order_id == order.id))
    if not calc:
        result = calculate_natal(
            birth_date=profile.birth_date, birth_time=profile.birth_time,
            time_accuracy=profile.time_accuracy,
            lat=profile.latitude, lon=profile.longitude, tz_id=profile.tz_id,
        )
        profile.utc_offset_used = result["utc_offset_used"]
        calc = NatalCalculation(
            order_id=order.id, birth_profile_id=profile.id,
            data=result["data"], warnings=result["warnings"],
        )
        session.add(calc)
        await session.commit()

    d = calc.data
    lines = [f"Имя: {profile.label}", f"Дата: {profile.birth_date}",
             f"Место: {profile.place_name}"]
    for planet, info in d.get("planets", {}).items():
        approx = " (приблизительно)" if info.get("approximate") else ""
        retro = " R" if info.get("retrograde") else ""
        lines.append(f"{planet}: {info['sign']} {info['degree_in_sign']}°{retro}{approx}")
    if "ascendant" in d:
        lines.append(f"Асцендент: {d['ascendant']['sign']}")
        lines.append(f"MC: {d['mc']['sign']}")
    if d.get("aspects"):
        lines.append("Аспекты: " + "; ".join(
            f"{a['a']}–{a['b']} {a['aspect']}" for a in d["aspects"][:20]))
    if calc.warnings:
        lines.append("Предупреждения: " + " ".join(calc.warnings))
    return "\n".join(lines)


async def generate_result(ctx: dict, order_id: int) -> None:
    settings = get_settings()
    attempt = ctx.get("job_try", 1)
    async with SessionMaker() as session:
        job = await session.scalar(
            select(GenerationJob).where(GenerationJob.order_id == order_id))
        order = await session.get(Order, order_id)
        if not job or not order:
            return
        if job.status in (JobStatus.completed, JobStatus.cancelled):
            return  # защита от повторной выдачи
        job.status = JobStatus.processing
        job.attempts = attempt
        await session.commit()

        bot = Bot(settings.bot_token,
                  default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        try:
            # --- данные для промпта ---
            if order.service.type == ServiceType.tarot:
                facts = await _prepare_tarot(session, order)
            else:
                facts = await _prepare_natal(session, order)

            prompt_row = await session.scalar(
                select(ServicePrompt).where(
                    ServicePrompt.service_id == order.service_id,
                    ServicePrompt.is_current.is_(True))
                .order_by(ServicePrompt.version.desc())
            )
            system_prompt = (prompt_row.system_prompt if prompt_row else
                             "Ты — профессиональный таролог и астролог. Отвечай по-русски.")
            template = (prompt_row.user_prompt_template if prompt_row else
                        "Данные:\n{facts}\n\nВопрос пользователя: {question}\n"
                        "Дай развёрнутую интерпретацию, общий вывод и рекомендации.")
            if prompt_row:
                if prompt_row.forbidden_topics:
                    system_prompt += f"\nЗапрещённые темы: {prompt_row.forbidden_topics}"
                if prompt_row.style_requirements:
                    system_prompt += f"\nСтиль: {prompt_row.style_requirements}"
                order.prompt_version_id = prompt_row.id

            template_values = {
                key: value
                for key, value in order.input_data.items()
                if isinstance(value, str) and key not in {"facts", "question"}
            }
            template_values.update(
                facts=facts,
                question=order.input_data.get("question", "—"),
            )
            user_prompt = (
                template.format(**template_values)
                if "{" in template
                else f"{template}\n\n{facts}"
            )

            # --- бюджет ---
            b = await budget.check_budget(session)
            if b["warn"]:
                await notify_admins(bot, b["warn"])
            if not b["allowed"]:
                raise openai_client.AIError("AI budget exceeded")
            model = settings.ai_model_fallback if b["use_fallback"] else None

            # --- генерация ---
            try:
                ai = await openai_client.generate(system_prompt, user_prompt, model=model)
                status = "ok"
            except openai_client.AIError:
                session.add(AIRequest(order_id=order.id, user_id=order.user_id,
                                      model=model or settings.ai_model_primary,
                                      status="error"))
                await session.commit()
                raise

            session.add(AIRequest(
                order_id=order.id, user_id=order.user_id, model=ai["model"],
                input_tokens=ai["input_tokens"], output_tokens=ai["output_tokens"],
                cost_usd=budget.estimate_cost(ai["model"], ai["input_tokens"],
                                              ai["output_tokens"]),
                status=status,
            ))

            disclaimer = await get_setting(session, "service_disclaimer")
            text = ai["text"][:order.service.max_output_chars]
            full_text = f"<b>{order.service.title}</b>\n\n{facts}\n\n{text}\n\n{disclaimer}"

            session.add(Result(order_id=order.id, user_id=order.user_id, text=full_text))
            order.status = OrderStatus.completed
            order.completed_at = datetime.now(timezone.utc)
            order.model_used = ai["model"]
            job.status = JobStatus.completed
            await session.commit()

            for i in range(0, len(full_text), 4000):
                await bot.send_message(order.user_id, full_text[i:i + 4000])

        except Exception as e:
            await log_error(session, "generation", e,
                            user_id=order.user_id, order_id=order.id)
            job.last_error = str(e)[:2000]
            if attempt < job.max_attempts:
                job.status = JobStatus.retrying
                await session.commit()
                delay = RETRY_DELAYS[min(attempt - 1, len(RETRY_DELAYS) - 1)]
                raise Retry(defer=delay) from e
            job.status = JobStatus.failed
            order.status = OrderStatus.failed
            await session.commit()
            await notify_admins(
                bot,
                f"❌ Генерация по заказу №{order.id} не удалась после {attempt} попыток: "
                f"{str(e)[:200]}"
            )
            try:
                await bot.send_message(
                    order.user_id,
                    "К сожалению, при формировании результата произошла ошибка. "
                    "Мы уже разбираемся; поддержка: /paysupport",
                )
            except Exception:
                pass
        finally:
            await bot.session.close()


async def send_broadcast(ctx: dict, broadcast_id: int) -> None:
    """Отправка рассылки с учётом отписок и блокировок."""
    from app.db.models import Broadcast, BroadcastRecipient
    from aiogram.exceptions import TelegramForbiddenError
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    settings = get_settings()
    bot = Bot(settings.bot_token,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    async with SessionMaker() as session:
        bc = await session.get(Broadcast, broadcast_id)
        if not bc or bc.status == "done":
            return
        bc.status = "running"
        await session.commit()

        recipients = (await session.scalars(
            select(BroadcastRecipient).where(
                BroadcastRecipient.broadcast_id == broadcast_id,
                BroadcastRecipient.status == "pending")
        )).all()

        buttons = [[InlineKeyboardButton(text=b["text"], url=b["url"])]
                   for b in (bc.buttons or []) if b.get("url")]
        buttons.append([InlineKeyboardButton(text="🔕 Отписаться",
                                             callback_data="unsub:broadcast")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)

        for r in recipients:
            user = await session.get(User, r.user_id)
            if not user or not user.subscribed or user.is_blocked_bot:
                r.status = "skipped"
                bc.unsubscribed_skipped += 1
                continue
            try:
                if bc.image_file_id:
                    await bot.send_photo(r.user_id, bc.image_file_id,
                                         caption=bc.text, reply_markup=kb)
                else:
                    await bot.send_message(r.user_id, bc.text, reply_markup=kb)
                r.status = "sent"
                bc.sent += 1
            except TelegramForbiddenError:
                r.status = "blocked"
                bc.blocked += 1
                user.is_blocked_bot = True
            except Exception as e:
                r.status = "error"
                r.error = str(e)[:500]
                bc.failed += 1
            await session.commit()
            await asyncio.sleep(0.05)  # ~20 сообщений в секунду

        bc.status = "done"
        await session.commit()
    await bot.session.close()


class WorkerSettings:
    functions = [generate_result, send_broadcast]
    redis_settings = RedisSettings(host=get_settings().redis_host,
                                   port=get_settings().redis_port)
    max_tries = 10  # ретраи управляются самим заданием через Retry
    job_timeout = 300
