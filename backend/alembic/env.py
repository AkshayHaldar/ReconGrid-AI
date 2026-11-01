import asyncio
import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.models  # noqa: F401 - ensure all ORM models are registered with Base.metadata
from app.core.config import settings
from app.core.database import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """Return database URL prioritizing DATABASE_URL from env, then settings, then alembic.ini."""
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        return env_url
    if settings.DATABASE_URL and not settings.DATABASE_URL.startswith("driver://"):
        return settings.DATABASE_URL
    ini_url = config.get_main_option("sqlalchemy.url")
    if ini_url and not ini_url.startswith("driver://"):
        return ini_url
    return "postgresql+asyncpg://recongrid:recongrid@localhost:5432/recongrid"


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    # If using async SQLite, use standard sqlite for offline DDL generation
    if url.startswith("sqlite+aiosqlite://"):
        url = url.replace("sqlite+aiosqlite://", "sqlite://", 1)

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode for asyncpg PostgreSQL."""
    url = get_url()
    connectable = create_async_engine(
        url,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    url = get_url()
    # For SQLite, standard Python sqlite3 is synchronous, reliable, and avoids thread locks
    if url.startswith("sqlite+aiosqlite://") or url.startswith("sqlite://"):
        sync_url = url.replace("sqlite+aiosqlite://", "sqlite://", 1)
        from sqlalchemy import create_engine

        connectable = create_engine(sync_url, poolclass=pool.NullPool)
        with connectable.connect() as connection:
            do_run_migrations(connection)
    elif "+asyncpg" in url:
        asyncio.run(run_async_migrations())
    else:
        from sqlalchemy import create_engine

        connectable = create_engine(url, poolclass=pool.NullPool)
        with connectable.connect() as connection:
            do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
