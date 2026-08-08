"""Создание/смена пароля администратора панели.

Запуск: docker compose run --rm bot python -m scripts.create_admin <login> <password> [telegram_id]
"""
import asyncio
import sys

from passlib.hash import bcrypt
from sqlalchemy import select

from app.db.models import AdminUser
from app.db.session import SessionMaker


async def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    login, password = sys.argv[1], sys.argv[2]
    tg_id = int(sys.argv[3]) if len(sys.argv) > 3 else None
    async with SessionMaker() as session:
        admin = await session.scalar(select(AdminUser).where(AdminUser.login == login))
        if admin:
            admin.password_hash = bcrypt.hash(password)
            admin.is_active = True
            print(f"Пароль администратора «{login}» обновлён")
        else:
            session.add(AdminUser(login=login, password_hash=bcrypt.hash(password),
                                  telegram_id=tg_id))
            print(f"Администратор «{login}» создан")
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
