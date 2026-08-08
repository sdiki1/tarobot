from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

engine = create_async_engine(get_settings().database_url, pool_size=10, max_overflow=20)
SessionMaker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
