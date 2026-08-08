"""Авторизация админ-панели: bcrypt-хеш, лимит попыток, журнал входов, сессии."""
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from passlib.hash import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import AdminAuditLog, AdminUser
from app.db.session import SessionMaker

MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 15

_serializer = URLSafeTimedSerializer(get_settings().admin_secret_key, salt="admin-session")


def make_session_cookie(admin_id: int) -> str:
    return _serializer.dumps({"admin_id": admin_id})


def read_session_cookie(value: str) -> int | None:
    try:
        data = _serializer.loads(
            value, max_age=get_settings().admin_session_ttl_minutes * 60)
        return data["admin_id"]
    except (BadSignature, KeyError):
        return None


async def get_db() -> AsyncSession:
    async with SessionMaker() as session:
        yield session


async def current_admin(request: Request,
                        session: AsyncSession = Depends(get_db)) -> AdminUser:
    cookie = request.cookies.get("admin_session")
    admin_id = read_session_cookie(cookie) if cookie else None
    admin = await session.get(AdminUser, admin_id) if admin_id else None
    if not admin or not admin.is_active:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return admin


async def try_login(session: AsyncSession, login: str, password: str) -> AdminUser | None:
    admin = await session.scalar(select(AdminUser).where(AdminUser.login == login))
    now = datetime.now(timezone.utc)
    if not admin or not admin.is_active:
        return None
    if admin.locked_until and now < admin.locked_until:
        return None
    if not bcrypt.verify(password, admin.password_hash):
        admin.failed_attempts += 1
        if admin.failed_attempts >= MAX_FAILED_ATTEMPTS:
            admin.locked_until = now + timedelta(minutes=LOCK_MINUTES)
            admin.failed_attempts = 0
        await session.commit()
        return None
    admin.failed_attempts = 0
    admin.locked_until = None
    session.add(AdminAuditLog(admin_user_id=admin.id, action="login"))
    await session.commit()
    return admin


async def audit(session: AsyncSession, admin: AdminUser, action: str,
                entity: str | None = None, entity_id=None, details: dict | None = None):
    session.add(AdminAuditLog(
        admin_user_id=admin.id, action=action, entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None,
        details=details or {},
    ))
