"""Админ-панель (FastAPI + Jinja2). Работает за Nginx с HTTPS."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import export, routes
from app.admin.auth import (
    current_admin, get_db, make_session_cookie, try_login,
)
from app.config import get_settings
from app.db.models import (
    AIRequest, GenerationJob, JobStatus, Order, OrderStatus, Payment, User,
)
from app.services.telegram_html import clean_telegram_html, visible_text
from app.services.texts import ALERT_LIMIT, PLACEHOLDERS

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Taro Bot Admin", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app.state.templates = templates

templates.env.globals.update(
    NAV=[
        ("/", "📊", "Главная"),
        ("/services", "🧾", "Услуги"),
        ("/orders", "📦", "Заказы"),
        ("/users", "👥", "Пользователи"),
        ("/promos", "🎟", "Промокоды"),
        ("/broadcasts", "📣", "Рассылки"),
        ("/settings", "✏️", "Тексты бота"),
    ],
    # статус -> (подпись, цвет бейджа)
    ORDER_STATUS={
        "created": ("Создан", ""), "invoiced": ("Ждёт оплаты", "yellow"),
        "paid": ("Оплачен", "blue"), "completed": ("Готов", "green"),
        "failed": ("Ошибка", "red"), "refunded": ("Возврат", "violet"),
        "cancelled": ("Отменён", ""),
    },
    JOB_STATUS={
        "queued": ("В очереди", ""), "processing": ("Выполняется", "blue"),
        "retrying": ("Повтор", "yellow"), "completed": ("Готово", "green"),
        "failed": ("Ошибка", "red"), "cancelled": ("Отменено", ""),
    },
    PLACEHOLDERS=PLACEHOLDERS,
    ALERT_LIMIT=ALERT_LIMIT,
    # сбрасывает кеш браузера при обновлении стилей и скриптов
    static_version=int(max(f.stat().st_mtime for f in STATIC_DIR.iterdir())),
)
# Текст Telegram как HTML страницы: разрешённые теги, всё остальное экранировано
templates.env.filters["tg_html"] = lambda text: Markup(clean_telegram_html(text or "")[0])
templates.env.filters["tg_plain"] = visible_text

app.include_router(routes.router)
app.include_router(export.router)


@app.exception_handler(302)
async def redirect_handler(request, exc):
    return RedirectResponse("/login")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login")
async def login_post(request: Request, login: str = Form(), password: str = Form(),
                     session: AsyncSession = Depends(get_db)):
    admin = await try_login(session, login, password)
    if not admin:
        return templates.TemplateResponse(
            request, "login.html", {"error": "Неверный логин или пароль (или вход заблокирован)."})
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie("admin_session", make_session_cookie(admin.id),
                    httponly=True, secure=get_settings().admin_cookie_secure,
                    samesite="lax")
    return resp


@app.get("/logout")
async def logout():
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("admin_session")
    return resp


@app.get("/health")
async def health(session: AsyncSession = Depends(get_db)):
    await session.execute(select(1))
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, admin=Depends(current_admin),
                    session: AsyncSession = Depends(get_db)):
    now = get_now()
    week_ago = now - timedelta(days=7)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    async def count(stmt):
        return await session.scalar(stmt) or 0

    stats = {
        "users_total": await count(select(func.count()).select_from(User)),
        "users_week": await count(select(func.count()).select_from(User)
                                  .where(User.created_at >= week_ago)),
        "orders_total": await count(select(func.count()).select_from(Order)),
        "payments_ok": await count(select(func.count()).select_from(Payment)
                                   .where(Payment.status == "paid")),
        "refunds": await count(select(func.count()).select_from(Payment)
                               .where(Payment.status == "refunded")),
        "stars_sum": await count(select(func.coalesce(func.sum(Payment.amount_stars), 0))
                                 .where(Payment.status == "paid")),
        "jobs_active": await count(select(func.count()).select_from(GenerationJob)
                                   .where(GenerationJob.status.in_(
                                       [JobStatus.queued, JobStatus.processing,
                                        JobStatus.retrying]))),
        "jobs_failed": await count(select(func.count()).select_from(GenerationJob)
                                   .where(GenerationJob.status == JobStatus.failed)),
        "ai_cost_month": float(await count(
            select(func.coalesce(func.sum(AIRequest.cost_usd), 0))
            .where(AIRequest.created_at >= month_start))),
    }
    return templates.TemplateResponse(request, "dashboard.html", {"stats": stats})


def get_now():
    return datetime.now(timezone.utc)
