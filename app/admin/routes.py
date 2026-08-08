"""CRUD-маршруты админ-панели: услуги, заказы, пользователи, промокоды,
рассылки, ошибки, настройки."""
import json
from datetime import datetime, timezone

from aiogram import Bot
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.auth import audit, current_admin, get_db
from app.config import get_settings
from app.db.models import (
    Broadcast, BroadcastRecipient, ErrorLog, GenerationJob, JobStatus, Order,
    OrderStatus, Payment, PromoCode, Refund, Result, Service, ServicePrompt,
    ServiceType, User,
)
from app.services.texts import DEFAULTS, get_setting, set_setting

router = APIRouter(dependencies=[Depends(current_admin)])


def tpl(request: Request):
    return request.app.state.templates


async def _enqueue(func_name: str, *args, job_id: str | None = None):
    s = get_settings()
    redis = await create_pool(RedisSettings(host=s.redis_host, port=s.redis_port))
    await redis.enqueue_job(func_name, *args, _job_id=job_id)
    await redis.close()


def _bot() -> Bot:
    return Bot(get_settings().bot_token)


# ---------- Услуги ----------

@router.get("/services", response_class=HTMLResponse)
async def services_list(request: Request, session: AsyncSession = Depends(get_db)):
    services = (await session.scalars(
        select(Service).where(Service.is_archived.is_(False)).order_by(Service.sort_order)
    )).all()
    return tpl(request).TemplateResponse(request, "services.html", {"services": services})


@router.get("/services/{service_id}", response_class=HTMLResponse)
async def service_edit(request: Request, service_id: int,
                       session: AsyncSession = Depends(get_db)):
    service = await session.get(Service, service_id) if service_id else None
    prompt = await session.scalar(
        select(ServicePrompt).where(ServicePrompt.service_id == service_id,
                                    ServicePrompt.is_current.is_(True))
        .order_by(ServicePrompt.version.desc())) if service else None
    return tpl(request).TemplateResponse(
        request, "service_form.html", {"s": service, "p": prompt})


@router.post("/services/{service_id}")
async def service_save(
    request: Request, service_id: int,
    session: AsyncSession = Depends(get_db), admin=Depends(current_admin),
    code: str = Form(), type_: str = Form(alias="type"), title: str = Form(),
    description: str = Form(""), price_stars: int = Form(),
    cards_count: int = Form(1), positions: str = Form(""),
    requires_question: bool = Form(False), required_fields: str = Form(""),
    allow_reversed: bool = Form(False), max_output_chars: int = Form(4000),
    per_user_daily_limit: int = Form(10), is_active: bool = Form(False),
    sort_order: int = Form(100),
    system_prompt: str = Form(""), user_prompt_template: str = Form(""),
    forbidden_topics: str = Form(""), style_requirements: str = Form(""),
):
    if service_id:
        service = await session.get(Service, service_id)
    else:
        service = Service(code=code, title=title, price_stars=price_stars)
        session.add(service)

    old_price = service.price_stars if service_id else None
    service.code = code
    service.type = ServiceType(type_)
    service.title = title
    service.description = description
    service.price_stars = price_stars
    service.cards_count = cards_count
    service.positions = [p.strip() for p in positions.split(",") if p.strip()]
    service.requires_question = requires_question
    service.required_fields = [f.strip() for f in required_fields.split(",") if f.strip()]
    service.allow_reversed = allow_reversed
    service.max_output_chars = max_output_chars
    service.per_user_daily_limit = per_user_daily_limit
    service.is_active = is_active
    service.sort_order = sort_order
    await session.flush()

    # Новая версия промпта при изменении текста
    current = await session.scalar(
        select(ServicePrompt).where(ServicePrompt.service_id == service.id,
                                    ServicePrompt.is_current.is_(True))
        .order_by(ServicePrompt.version.desc()))
    changed = (not current or current.system_prompt != system_prompt
               or current.user_prompt_template != user_prompt_template
               or current.forbidden_topics != forbidden_topics
               or current.style_requirements != style_requirements)
    if changed and (system_prompt or user_prompt_template):
        if current:
            current.is_current = False
        session.add(ServicePrompt(
            service_id=service.id, version=(current.version + 1 if current else 1),
            system_prompt=system_prompt, user_prompt_template=user_prompt_template,
            forbidden_topics=forbidden_topics, style_requirements=style_requirements,
        ))
        await audit(session, admin, "prompt_change", "service", service.id)
    if old_price is not None and old_price != price_stars:
        await audit(session, admin, "price_change", "service", service.id,
                    {"old": old_price, "new": price_stars})
    await session.commit()
    return RedirectResponse("/services", status_code=302)


@router.post("/services/{service_id}/archive")
async def service_archive(service_id: int, session: AsyncSession = Depends(get_db),
                          admin=Depends(current_admin)):
    service = await session.get(Service, service_id)
    service.is_archived = True
    service.is_active = False
    await audit(session, admin, "service_archive", "service", service_id)
    await session.commit()
    return RedirectResponse("/services", status_code=302)


# ---------- Заказы ----------

@router.get("/orders", response_class=HTMLResponse)
async def orders_list(request: Request, status: str = "",
                      session: AsyncSession = Depends(get_db)):
    stmt = select(Order).order_by(Order.created_at.desc()).limit(200)
    if status:
        stmt = stmt.where(Order.status == OrderStatus(status))
    orders = (await session.scalars(stmt)).all()
    return tpl(request).TemplateResponse(
        request, "orders.html", {"orders": orders, "status": status})


@router.get("/orders/{order_id}", response_class=HTMLResponse)
async def order_detail(request: Request, order_id: int,
                       session: AsyncSession = Depends(get_db)):
    order = await session.get(Order, order_id)
    job = await session.scalar(select(GenerationJob)
                               .where(GenerationJob.order_id == order_id))
    payment = await session.scalar(select(Payment).where(Payment.order_id == order_id))
    result = await session.scalar(select(Result).where(Result.order_id == order_id))
    errors = (await session.scalars(
        select(ErrorLog).where(ErrorLog.order_id == order_id)
        .order_by(ErrorLog.created_at.desc()).limit(10))).all()
    return tpl(request).TemplateResponse(request, "order_detail.html", {
        "o": order, "job": job, "payment": payment, "result": result, "errors": errors,
        "input_json": json.dumps(order.input_data, ensure_ascii=False, indent=1),
    })


@router.post("/orders/{order_id}/retry")
async def order_retry(order_id: int, session: AsyncSession = Depends(get_db),
                      admin=Depends(current_admin)):
    job = await session.scalar(select(GenerationJob)
                               .where(GenerationJob.order_id == order_id))
    if job:
        job.status = JobStatus.queued
        job.attempts = 0
    order = await session.get(Order, order_id)
    if order.status == OrderStatus.failed:
        order.status = OrderStatus.paid
    await audit(session, admin, "regenerate", "order", order_id)
    await session.commit()
    await _enqueue("generate_result", order_id,
                   job_id=f"order-{order_id}-retry-{datetime.now().timestamp():.0f}")
    return RedirectResponse(f"/orders/{order_id}", status_code=302)


@router.post("/orders/{order_id}/resend")
async def order_resend(order_id: int, session: AsyncSession = Depends(get_db),
                       admin=Depends(current_admin)):
    result = await session.scalar(select(Result).where(Result.order_id == order_id))
    if result:
        bot = _bot()
        try:
            for i in range(0, len(result.text), 4000):
                await bot.send_message(result.user_id, result.text[i:i + 4000],
                                       parse_mode="HTML")
        finally:
            await bot.session.close()
        await audit(session, admin, "resend_result", "order", order_id)
        await session.commit()
    return RedirectResponse(f"/orders/{order_id}", status_code=302)


@router.post("/orders/{order_id}/cancel")
async def order_cancel(order_id: int, session: AsyncSession = Depends(get_db),
                       admin=Depends(current_admin)):
    job = await session.scalar(select(GenerationJob)
                               .where(GenerationJob.order_id == order_id))
    if job:
        job.status = JobStatus.cancelled
    await audit(session, admin, "cancel_job", "order", order_id)
    await session.commit()
    return RedirectResponse(f"/orders/{order_id}", status_code=302)


@router.post("/orders/{order_id}/comment")
async def order_comment(order_id: int, comment: str = Form(""),
                        session: AsyncSession = Depends(get_db),
                        admin=Depends(current_admin)):
    order = await session.get(Order, order_id)
    order.admin_comment = comment
    await session.commit()
    return RedirectResponse(f"/orders/{order_id}", status_code=302)


@router.post("/orders/{order_id}/refund")
async def order_refund(order_id: int, reason: str = Form(""),
                       session: AsyncSession = Depends(get_db),
                       admin=Depends(current_admin)):
    payment = await session.scalar(select(Payment).where(Payment.order_id == order_id))
    if not payment or payment.status == "refunded":
        return RedirectResponse(f"/orders/{order_id}", status_code=302)
    bot = _bot()
    try:
        await bot.refund_star_payment(
            user_id=payment.user_id,
            telegram_payment_charge_id=payment.telegram_payment_charge_id,
        )
    finally:
        await bot.session.close()
    payment.status = "refunded"
    payment.refunded_at = datetime.now(timezone.utc)
    payment.refund_reason = reason
    order = await session.get(Order, order_id)
    order.status = OrderStatus.refunded
    session.add(Refund(payment_id=payment.id, admin_user_id=admin.id, reason=reason))
    await audit(session, admin, "refund", "order", order_id, {"reason": reason})
    await session.commit()
    return RedirectResponse(f"/orders/{order_id}", status_code=302)


# ---------- Пользователи ----------

@router.get("/users", response_class=HTMLResponse)
async def users_list(request: Request, q: str = "",
                     session: AsyncSession = Depends(get_db)):
    stmt = select(User).order_by(User.created_at.desc()).limit(100)
    if q:
        if q.isdigit():
            stmt = select(User).where(User.id == int(q))
        else:
            stmt = select(User).where(User.username.ilike(f"%{q}%")).limit(100)
    users = (await session.scalars(stmt)).all()
    return tpl(request).TemplateResponse(request, "users.html", {"users": users, "q": q})


@router.post("/users/{user_id}/toggle_ban")
async def user_toggle_ban(user_id: int, session: AsyncSession = Depends(get_db),
                          admin=Depends(current_admin)):
    user = await session.get(User, user_id)
    user.is_banned = not user.is_banned
    await audit(session, admin, "user_ban_toggle", "user", user_id,
                {"banned": user.is_banned})
    await session.commit()
    return RedirectResponse("/users", status_code=302)


@router.post("/users/{user_id}/message")
async def user_message(user_id: int, text: str = Form(),
                       session: AsyncSession = Depends(get_db),
                       admin=Depends(current_admin)):
    bot = _bot()
    try:
        await bot.send_message(user_id, text)
    finally:
        await bot.session.close()
    await audit(session, admin, "service_message", "user", user_id)
    await session.commit()
    return RedirectResponse("/users", status_code=302)


# ---------- Промокоды ----------

@router.get("/promos", response_class=HTMLResponse)
async def promos_list(request: Request, session: AsyncSession = Depends(get_db)):
    promos = (await session.scalars(select(PromoCode).order_by(PromoCode.id.desc()))).all()
    return tpl(request).TemplateResponse(request, "promos.html", {"promos": promos})


@router.post("/promos")
async def promo_create(
    session: AsyncSession = Depends(get_db), admin=Depends(current_admin),
    code: str = Form(), discount_percent: str = Form(""), discount_stars: str = Form(""),
    max_activations: str = Form(""), per_user_limit: int = Form(1),
    min_order_stars: int = Form(0), starts_at: str = Form(""), ends_at: str = Form(""),
):
    session.add(PromoCode(
        code=code.strip(),
        discount_percent=int(discount_percent) if discount_percent else None,
        discount_stars=int(discount_stars) if discount_stars else None,
        max_activations=int(max_activations) if max_activations else None,
        per_user_limit=per_user_limit, min_order_stars=min_order_stars,
        starts_at=datetime.fromisoformat(starts_at) if starts_at else None,
        ends_at=datetime.fromisoformat(ends_at) if ends_at else None,
    ))
    await audit(session, admin, "promo_create", "promo", code)
    await session.commit()
    return RedirectResponse("/promos", status_code=302)


@router.post("/promos/{promo_id}/toggle")
async def promo_toggle(promo_id: int, session: AsyncSession = Depends(get_db),
                       admin=Depends(current_admin)):
    promo = await session.get(PromoCode, promo_id)
    promo.is_active = not promo.is_active
    await audit(session, admin, "promo_toggle", "promo", promo_id)
    await session.commit()
    return RedirectResponse("/promos", status_code=302)


# ---------- Рассылки ----------

AUDIENCES = {
    "all": "Все активные",
    "with_orders": "С заказами",
    "without_orders": "Без заказов",
}


@router.get("/broadcasts", response_class=HTMLResponse)
async def broadcasts_list(request: Request, session: AsyncSession = Depends(get_db)):
    items = (await session.scalars(
        select(Broadcast).order_by(Broadcast.id.desc()).limit(50))).all()
    return tpl(request).TemplateResponse(
        request, "broadcasts.html", {"items": items, "audiences": AUDIENCES})


@router.post("/broadcasts")
async def broadcast_create(
    session: AsyncSession = Depends(get_db), admin=Depends(current_admin),
    text: str = Form(), audience: str = Form("all"),
    button_text: str = Form(""), button_url: str = Form(""),
    test_only: bool = Form(False),
):
    buttons = [{"text": button_text, "url": button_url}] if button_text and button_url else []
    if test_only:
        bot = _bot()
        try:
            for admin_id in get_settings().admin_ids:
                await bot.send_message(admin_id, f"[ТЕСТ РАССЫЛКИ]\n\n{text}")
        finally:
            await bot.session.close()
        return RedirectResponse("/broadcasts", status_code=302)

    bc = Broadcast(text=text, buttons=buttons, audience_filter={"type": audience})
    session.add(bc)
    await session.flush()

    stmt = select(User.id).where(User.subscribed.is_(True), User.is_blocked_bot.is_(False),
                                 User.is_banned.is_(False), User.deleted_at.is_(None))
    if audience == "with_orders":
        stmt = stmt.where(User.id.in_(select(Order.user_id)))
    elif audience == "without_orders":
        stmt = stmt.where(User.id.notin_(select(Order.user_id)))
    user_ids = (await session.scalars(stmt)).all()
    for uid in user_ids:
        session.add(BroadcastRecipient(broadcast_id=bc.id, user_id=uid))
    bc.total = len(user_ids)
    await audit(session, admin, "broadcast_start", "broadcast", bc.id)
    await session.commit()
    await _enqueue("send_broadcast", bc.id, job_id=f"broadcast-{bc.id}")
    return RedirectResponse("/broadcasts", status_code=302)


# ---------- Ошибки ----------

@router.get("/errors", response_class=HTMLResponse)
async def errors_list(request: Request, session: AsyncSession = Depends(get_db)):
    errors = (await session.scalars(
        select(ErrorLog).order_by(ErrorLog.created_at.desc()).limit(100))).all()
    return tpl(request).TemplateResponse(request, "errors.html", {"errors": errors})


@router.post("/errors/{error_id}/resolve")
async def error_resolve(error_id: int, comment: str = Form(""),
                        session: AsyncSession = Depends(get_db)):
    err = await session.get(ErrorLog, error_id)
    err.is_resolved = True
    err.admin_comment = comment
    await session.commit()
    return RedirectResponse("/errors", status_code=302)


# ---------- Настройки и тексты ----------

@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, session: AsyncSession = Depends(get_db)):
    values = {k: await get_setting(session, k) for k in DEFAULTS}
    return tpl(request).TemplateResponse(request, "settings.html", {"values": values})


@router.post("/settings")
async def settings_save(request: Request, session: AsyncSession = Depends(get_db),
                        admin=Depends(current_admin)):
    form = await request.form()
    for key in DEFAULTS:
        if key in form:
            await set_setting(session, key, str(form[key]))
    await audit(session, admin, "settings_change")
    await session.commit()
    return RedirectResponse("/settings", status_code=302)
