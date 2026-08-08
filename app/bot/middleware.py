"""Создаёт/обновляет пользователя и открывает сессию БД для каждого апдейта."""
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from sqlalchemy import func

from app.db.models import User
from app.db.session import SessionMaker


class DbUserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        async with SessionMaker() as session:
            db_user = None
            if tg_user and not tg_user.is_bot:
                db_user = await session.get(User, tg_user.id)
                if db_user is None:
                    db_user = User(
                        id=tg_user.id,
                        username=tg_user.username,
                        first_name=tg_user.first_name,
                    )
                    session.add(db_user)
                else:
                    db_user.username = tg_user.username
                    db_user.first_name = tg_user.first_name
                    db_user.last_active_at = func.now()
                    db_user.is_blocked_bot = False
                await session.commit()
                if db_user.is_banned:
                    return None  # доступ отключён администратором
            data["session"] = session
            data["db_user"] = db_user
            return await handler(event, data)
