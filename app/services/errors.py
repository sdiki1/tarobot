"""Журнал ошибок. Секреты и платёжные данные в журнал не пишутся."""
import re
import traceback as tb_mod

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ErrorLog

_SECRET_RE = re.compile(r"(api[_-]?key|token|password|secret)[\"'=:\s]+\S+", re.I)


def _scrub(text: str) -> str:
    return _SECRET_RE.sub(r"\1=***", text or "")


async def log_error(
    session: AsyncSession,
    component: str,
    exc: BaseException | None = None,
    message: str = "",
    user_id: int | None = None,
    order_id: int | None = None,
) -> None:
    session.add(ErrorLog(
        component=component,
        error_type=type(exc).__name__ if exc else "Error",
        message=_scrub(message or (str(exc) if exc else "")),
        traceback=_scrub("".join(tb_mod.format_exception(exc))) if exc else None,
        user_id=user_id,
        order_id=order_id,
    ))
