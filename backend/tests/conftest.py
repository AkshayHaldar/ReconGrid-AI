"""Pytest async configuration and test database fixtures."""

import asyncio
import os
from typing import AsyncGenerator
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.database import Base, get_db, engine_args
from app.main import app

DEFAULT_SQLITE_URL = "sqlite+aiosqlite:///./test_recongrid.db"
DEFAULT_POSTGRES_URL = "postgresql+asyncpg://recongrid:recongrid@localhost:5432/recongrid"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--postgres",
        action="store_true",
        default=False,
        help="Run test suite against PostgreSQL database instead of SQLite",
    )


def get_test_database_url(pytestconfig: pytest.Config | None = None) -> str:
    if os.environ.get("TEST_DATABASE_URL"):
        return os.environ["TEST_DATABASE_URL"]
    if pytestconfig and pytestconfig.getoption("--postgres", default=False):
        return os.environ.get("POSTGRES_TEST_DATABASE_URL", DEFAULT_POSTGRES_URL)
    return DEFAULT_SQLITE_URL


def get_engine_args_for_url(db_url: str) -> dict:
    args = dict(engine_args)
    if db_url.startswith("sqlite"):
        args["connect_args"] = {"check_same_thread": False}
    else:
        args.pop("connect_args", None)
    return args


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
async def setup_test_database(pytestconfig: pytest.Config):
    test_db_url = get_test_database_url(pytestconfig)
    curr_engine_args = get_engine_args_for_url(test_db_url)
    engine = create_async_engine(test_db_url, **curr_engine_args)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(pytestconfig: pytest.Config) -> AsyncGenerator[AsyncSession, None]:
    test_db_url = get_test_database_url(pytestconfig)
    curr_engine_args = get_engine_args_for_url(test_db_url)
    engine = create_async_engine(test_db_url, **curr_engine_args)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.commit()
    await engine.dispose()
