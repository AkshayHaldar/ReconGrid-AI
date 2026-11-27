"""lock_batch picks the right primitive per dialect and keys PostgreSQL locks per batch."""

import sqlite3
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.locks import BATCH_LOCK_NAMESPACE, batch_lock_key, lock_batch


def test_batch_lock_key_is_stable_per_batch_and_fits_int4():
    # Fixed values: every API and worker process must derive the same key, so no randomized hash().
    assert batch_lock_key("default") == 933818049
    assert batch_lock_key("march-2026") == -1845326068
    for batch_id in ("default", "march-2026", "", "x" * 500, "बैच"):
        assert -(2**31) <= batch_lock_key(batch_id) < 2**31


@pytest.mark.asyncio
async def test_postgres_takes_a_transaction_advisory_lock_keyed_by_batch():
    session = MagicMock()
    session.bind.dialect.name = "postgresql"
    session.execute = AsyncMock()

    await lock_batch(session, "march-2026")

    statement, params = session.execute.await_args.args
    assert str(statement) == "SELECT pg_advisory_xact_lock(:namespace, :key)"
    assert params == {"namespace": BATCH_LOCK_NAMESPACE, "key": batch_lock_key("march-2026")}


@pytest.mark.asyncio
async def test_unknown_bind_is_left_alone():
    session = AsyncMock()  # what the RazorpayClient unit tests pass in
    await lock_batch(session, "default")
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_sqlite_holds_the_write_lock_until_commit_and_is_reentrant(tmp_path):
    path = tmp_path / "lock.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE t (x INTEGER)"))
        async with async_sessionmaker(bind=engine, class_=AsyncSession)() as session:
            await session.execute(text("SELECT 1"))  # a plain read first, as the record routes do
            await lock_batch(session, "default")
            await session.execute(text("INSERT INTO t VALUES (1)"))
            await lock_batch(session, "default")  # already writing: no nested BEGIN

            other = sqlite3.connect(path, timeout=0.1)
            try:
                with pytest.raises(sqlite3.OperationalError, match="locked"):
                    other.execute("BEGIN IMMEDIATE")
                await session.commit()
                other.execute("BEGIN IMMEDIATE")
                assert other.execute("SELECT x FROM t").fetchall() == [(1,)]
                other.rollback()
            finally:
                other.close()
    finally:
        await engine.dispose()
