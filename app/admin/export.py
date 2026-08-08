"""Экспорт данных в CSV и XLSX с фильтрацией по периоду."""
import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.auth import current_admin, get_db
from app.db.models import (
    AIRequest, Order, Payment, PromoActivation, Refund, User,
)

router = APIRouter(prefix="/export", dependencies=[Depends(current_admin)])

EXPORTS = {
    "users": (User, ["id", "username", "first_name", "created_at", "last_active_at",
                     "subscribed", "is_blocked_bot", "is_banned"]),
    "orders": (Order, ["id", "user_id", "service_id", "status", "price_stars",
                       "final_price_stars", "created_at", "completed_at"]),
    "payments": (Payment, ["id", "order_id", "user_id", "amount_stars", "currency",
                           "telegram_payment_charge_id", "status", "created_at",
                           "refunded_at"]),
    "refunds": (Refund, ["id", "payment_id", "admin_user_id", "reason", "created_at"]),
    "ai_costs": (AIRequest, ["id", "order_id", "user_id", "model", "input_tokens",
                             "output_tokens", "cost_usd", "status", "created_at"]),
    "promo_activations": (PromoActivation, ["id", "promo_code_id", "user_id",
                                            "order_id", "created_at"]),
}


async def _rows(session: AsyncSession, entity: str, date_from: str, date_to: str):
    model, fields = EXPORTS[entity]
    stmt = select(model)
    if date_from and hasattr(model, "created_at"):
        stmt = stmt.where(model.created_at >= datetime.fromisoformat(date_from))
    if date_to and hasattr(model, "created_at"):
        stmt = stmt.where(model.created_at <= datetime.fromisoformat(date_to))
    items = (await session.scalars(stmt)).all()
    yield fields
    for item in items:
        yield [str(getattr(item, f) or "") for f in fields]


@router.get("/{entity}.csv")
async def export_csv(entity: str, date_from: str = "", date_to: str = "",
                     session: AsyncSession = Depends(get_db)):
    if entity not in EXPORTS:
        return {"error": "unknown entity"}
    buf = io.StringIO()
    writer = csv.writer(buf)
    async for row in _rows(session, entity, date_from, date_to):
        writer.writerow(row)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={entity}.csv"})


@router.get("/{entity}.xlsx")
async def export_xlsx(entity: str, date_from: str = "", date_to: str = "",
                      session: AsyncSession = Depends(get_db)):
    if entity not in EXPORTS:
        return {"error": "unknown entity"}
    wb = Workbook()
    ws = wb.active
    async for row in _rows(session, entity, date_from, date_to):
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={entity}.xlsx"})
