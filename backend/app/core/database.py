"""SQLAlchemy asynchronous database session and engine setup."""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings


class Base(DeclarativeBase):
    pass


import json
from datetime import date, datetime
from decimal import Decimal

def _custom_json_serializer(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

def json_dumps(obj):
    return json.dumps(obj, default=_custom_json_serializer)

# Configure engine with SQLite and PostgreSQL connection pool compatibility
engine_args = {
    "echo": False,
    "future": True,
    "json_serializer": json_dumps,
}

if settings.DATABASE_URL.startswith("sqlite"):
    engine_args["connect_args"] = {"check_same_thread": False}

engine: AsyncEngine = create_async_engine(settings.DATABASE_URL, **engine_args)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for obtaining an isolated async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initializes schema tables on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
