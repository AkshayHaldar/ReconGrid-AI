"""Per-batch write lock shared by every path that rewrites a batch's reconciliation snapshot."""

import hashlib

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# First half of the two-key PostgreSQL advisory lock. It used to be the single global webhook key;
# the second half is derived from the batch id, so different batches no longer wait on each other.
BATCH_LOCK_NAMESPACE = 1380405828


def batch_lock_key(batch_id: str) -> int:
    """Signed 32-bit key for a batch id, identical in every process (unlike Python's randomized hash())."""
    digest = hashlib.sha256(batch_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big", signed=True)


def _dialect_name(session: AsyncSession) -> str:
    bind = session.bind if session.bind is not None else session.get_bind()
    return bind.dialect.name


async def lock_batch(session: AsyncSession, batch_id: str) -> None:
    """Block until no other transaction holds the write lock of this batch; held until commit/rollback.

    Call it before reading the rows the write depends on, so the snapshot read afterwards is current.
    PostgreSQL takes pg_advisory_xact_lock(namespace, key(batch_id)), so only writers of the same batch
    queue up. SQLite has one writer per database, so BEGIN IMMEDIATE takes that write lock up front;
    a connection that already wrote in this transaction holds it already and is left alone.
    """
    dialect = _dialect_name(session)
    if dialect == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:namespace, :key)"),
            {"namespace": BATCH_LOCK_NAMESPACE, "key": batch_lock_key(batch_id)},
        )
    elif dialect == "sqlite":
        connection = await session.connection()
        driver = (await connection.get_raw_connection()).driver_connection
        if driver is None or not driver.in_transaction:
            await session.execute(text("BEGIN IMMEDIATE"))


# Second key reserved for the ledger-wide freeze lock (two-int form, same namespace as the batch locks).
_FREEZE_NAMESPACE = BATCH_LOCK_NAMESPACE + 1


async def lock_ledger_freeze(session: AsyncSession, *, exclusive: bool = False) -> None:
    """Keep sign-offs and settlement writes apart; held until commit/rollback.

    Settlements and refunds are shared by all batches, so writers of them take this lock shared and a
    sign-off takes it exclusive. Always take it before any batch lock. SQLite uses its single write lock.
    """
    dialect = _dialect_name(session)
    if dialect == "postgresql":
        function = "pg_advisory_xact_lock" if exclusive else "pg_advisory_xact_lock_shared"
        await session.execute(text(f"SELECT {function}(:namespace, 0)"), {"namespace": _FREEZE_NAMESPACE})
    elif dialect == "sqlite":
        await lock_batch(session, "")
