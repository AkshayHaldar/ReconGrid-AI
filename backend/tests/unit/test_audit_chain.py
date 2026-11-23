"""SHA-256 audit chain on reconciliation_logs: hashing, tamper detection, manual actions, certificate, migration."""

import hashlib
import hmac
import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.main import app
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.models.reconciliation_log import ReconciliationLog, compute_entry_hash
from app.repositories.reconciliation_repo import ReconciliationRepository
from app.services.reconciliation import (
    ReconciliationEngine,
    build_audit_certificate,
    verify_batch_audit_chain,
)

BATCH = "audit_batch"


async def _seed_and_reconcile(session: AsyncSession, batch_id: str = BATCH, count: int = 4):
    """Bank rows with matching settlements (TIER_1) plus one old unmatched row (EXCEPTION)."""
    now = datetime.now(UTC)
    txs, setls = [], []
    for i in range(count):
        amount = Decimal(f"{10000 + i * 1000}.00")
        txs.append(
            BankTransaction(
                date=now - timedelta(days=1),
                amount=amount,
                direction="CREDIT",
                utr=f"CMSAUDIT{batch_id[:3].upper()}{i:04d}",
                description=f"CMS/AUDIT{i}/HDFC/PAYOUT",
                row_hash=f"hash-{batch_id}-{i}",
                batch_id=batch_id,
            )
        )
        setls.append(
            RazorpaySettlement(
                settlement_id=f"setl_{batch_id}_{i}",
                amount=amount,
                gross_amount=amount,
                fees=Decimal("0.00"),
                tax=Decimal("0.00"),
                utr=f"CMSAUDIT{batch_id[:3].upper()}{i:04d}",
                status="processed",
                settlement_created_at=now - timedelta(hours=12),
                raw_payload={},
                is_test_mode=True,
            )
        )
    txs.append(
        BankTransaction(
            date=now - timedelta(days=60),
            amount=Decimal("777.00"),
            direction="CREDIT",
            utr="ZZZUNMATCHED001",
            description="UNKNOWN CREDIT",
            row_hash=f"hash-{batch_id}-orphan",
            batch_id=batch_id,
        )
    )
    session.add_all([*txs, *setls])
    await session.flush()
    engine = ReconciliationEngine(ReconciliationRepository(session))
    logs = await engine.reconcile_batch(txs, setls, batch_id=batch_id)
    await session.commit()
    return txs, setls, logs


async def _verify(session: AsyncSession, batch_id: str = BATCH):
    return await verify_batch_audit_chain(ReconciliationRepository(session), batch_id)


@pytest.mark.asyncio
async def test_engine_logs_form_a_valid_chain(db_session: AsyncSession):
    _, _, logs = await _seed_and_reconcile(db_session)

    assert len(logs) == 5
    chain = (await db_session.execute(select(ReconciliationLog).order_by(ReconciliationLog.created_at))).scalars().all()
    assert chain[0].previous_hash is None
    for prev, nxt in zip(chain, chain[1:]):
        assert nxt.previous_hash == prev.compute_link_hash()
    for log in chain:
        assert len(log.entry_hash) == 64
        assert log.entry_hash == compute_entry_hash(log._values(), log.previous_hash)

    result = await _verify(db_session)
    assert (result.status, result.tampered, result.total_records) == ("VERIFIED", False, 5)
    assert result.chain_head == chain[-1].compute_link_hash()


@pytest.mark.asyncio
async def test_entry_hash_is_deterministic(db_session: AsyncSession):
    _, _, logs = await _seed_and_reconcile(db_session)
    log = logs[0]
    assert log.compute_entry_hash() == log.compute_entry_hash() == log.entry_hash
    # Same values, different predecessor -> different hash.
    assert compute_entry_hash(log._values(), "f" * 64) != log.entry_hash


@pytest.mark.asyncio
async def test_empty_batch_verifies(db_session: AsyncSession):
    result = await _verify(db_session, "no_such_batch")
    assert (result.status, result.tampered, result.total_records) == ("VERIFIED", False, 0)


@pytest.mark.asyncio
async def test_modifying_amount_in_database_is_detected(db_session: AsyncSession):
    _, _, logs = await _seed_and_reconcile(db_session)
    victim = logs[2]
    original_hash = victim.entry_hash

    await db_session.execute(
        text("UPDATE reconciliation_logs SET delta_amount = :amt WHERE id = :id"),
        {"amt": "123456.78", "id": victim.id},
    )
    await db_session.commit()

    result = await _verify(db_session)
    assert result.status == "COMPROMISED"
    assert result.tampered is True
    assert result.failed_at_id == victim.id
    assert result.actual_hash == original_hash
    assert result.expected_hash != original_hash
    assert result.reason == "ENTRY_HASH_MISMATCH"


@pytest.mark.parametrize(
    "column,value",
    [
        ("match_status", "MATCHED"),
        ("match_tier", "TIER_9"),
        ("confidence_score", "0.01"),
        ("diagnostic_type", "FEE_DEDUCTION"),
        ("diagnostic_note", "edited by dba"),
        ("human_action", "APPROVED"),
        ("batch_id", "audit_batch"),  # same value on purpose: no-op must stay VERIFIED
        ("matched_at", "2020-01-01 00:00:00.000000"),
        ("rzp_settlement_id", None),
    ],
)
@pytest.mark.asyncio
async def test_editing_any_audited_field_is_detected(db_session: AsyncSession, column: str, value):
    _, _, logs = await _seed_and_reconcile(db_session)
    # the unmatched exception row (last) has no settlement and no confidence; pick a matched one instead
    victim = logs[1]
    before = await db_session.execute(
        text(f"SELECT {column} FROM reconciliation_logs WHERE id = :id"), {"id": victim.id}
    )
    unchanged = before.scalar() == value

    await db_session.execute(
        text(f"UPDATE reconciliation_logs SET {column} = :v WHERE id = :id"), {"v": value, "id": victim.id}
    )
    await db_session.commit()

    result = await _verify(db_session)
    if unchanged:
        assert result.status == "VERIFIED"
    else:
        assert result.status == "COMPROMISED"
        assert result.failed_at_id == victim.id


@pytest.mark.asyncio
async def test_deleted_row_breaks_the_link(db_session: AsyncSession):
    _, _, _ = await _seed_and_reconcile(db_session)
    chain = (await db_session.execute(select(ReconciliationLog).order_by(ReconciliationLog.created_at))).scalars().all()
    middle, successor = chain[2], chain[3]

    await db_session.execute(text("DELETE FROM reconciliation_logs WHERE id = :id"), {"id": middle.id})
    await db_session.commit()

    result = await _verify(db_session)
    assert result.status == "COMPROMISED"
    assert result.failed_at_id == successor.id
    assert result.reason == "BROKEN_CHAIN_LINK"
    assert result.expected_hash == chain[1].compute_link_hash()
    assert result.actual_hash == middle.compute_link_hash()


@pytest.mark.asyncio
async def test_editing_created_at_is_detected(db_session: AsyncSession):
    """created_at is part of the row's identity, so moving a row in the chain order is caught."""
    _, _, logs = await _seed_and_reconcile(db_session)
    victim = logs[1]
    await db_session.execute(
        text("UPDATE reconciliation_logs SET created_at = :ts WHERE id = :id"),
        {"ts": "2030-01-01 00:00:00.000000", "id": victim.id},
    )
    await db_session.commit()
    result = await _verify(db_session)
    assert result.status == "COMPROMISED"


@pytest.mark.asyncio
async def test_rerun_supersedes_old_logs_but_chain_stays_valid(db_session: AsyncSession):
    txs, setls, first = await _seed_and_reconcile(db_session)
    engine = ReconciliationEngine(ReconciliationRepository(db_session))
    second = await engine.reconcile_batch(txs, setls, batch_id=BATCH)
    await db_session.commit()

    result = await _verify(db_session)
    assert result.status == "VERIFIED"
    assert result.total_records == len(first) + len(second)
    # the second run continues the same chain rather than starting a new one
    assert second[0].previous_hash is not None
    superseded = (
        (await db_session.execute(select(ReconciliationLog).where(ReconciliationLog.superseded == True)))
        .scalars()
        .all()
    )  # noqa: E712
    assert len(superseded) == len(first)


@pytest.mark.asyncio
async def test_batches_have_independent_chains(db_session: AsyncSession):
    await _seed_and_reconcile(db_session, "alpha_batch", count=2)
    await _seed_and_reconcile(db_session, "beta_batch", count=3)
    assert (await _verify(db_session, "alpha_batch")).total_records == 3
    assert (await _verify(db_session, "beta_batch")).total_records == 4
    genesis = (
        (await db_session.execute(select(ReconciliationLog).where(ReconciliationLog.previous_hash.is_(None))))
        .scalars()
        .all()
    )
    assert sorted(g.batch_id for g in genesis) == ["alpha_batch", "beta_batch"]


@pytest.mark.asyncio
async def test_log_added_without_hash_fields_still_gets_chained(db_session: AsyncSession):
    """Rows added through plain ORM construction (no engine) are sealed by the before_flush hook."""
    tx = BankTransaction(
        date=datetime.now(UTC),
        amount=Decimal("50.00"),
        direction="CREDIT",
        description="plain orm",
        row_hash="plain-orm-1",
        batch_id="plain_batch",
    )
    db_session.add(tx)
    await db_session.flush()
    for _ in range(2):
        db_session.add(
            ReconciliationLog(bank_tx_id=tx.id, batch_id="plain_batch", match_status="EXCEPTION", match_tier="TIER_3")
        )
    await db_session.commit()
    result = await _verify(db_session, "plain_batch")
    assert (result.status, result.total_records) == ("VERIFIED", 2)


# --- manual actions edit rows in place; they must re-seal, not break the chain ---


async def _api_batch(client: AsyncClient, batch_id: str = "default"):
    await client.post("/api/v1/demo/seed?count=15")
    resp = await client.get(f"/api/v1/reconciliation/{batch_id}/records?status=ALL&page_size=200")
    return resp.json()["data"]["records"]


async def _verify_api(client: AsyncClient, batch_id: str = "default") -> dict:
    resp = await client.get(f"/api/v1/reconciliation/{batch_id}/verify-audit-chain")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    return body["data"]


@pytest.mark.asyncio
async def test_manual_actions_keep_chain_verified(db_session: AsyncSession):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        records = await _api_batch(client)
        assert (await _verify_api(client))["status"] == "VERIFIED"

        rec_id = records[0]["id"]
        assert (
            await client.post(f"/api/v1/reconciliation/records/{rec_id}/approve", json={"note": "ok"})
        ).status_code == 200
        assert (await _verify_api(client))["status"] == "VERIFIED"

        assert (
            await client.post(f"/api/v1/reconciliation/records/{rec_id}/deny", json={"note": "no"})
        ).status_code == 200
        assert (await _verify_api(client))["status"] == "VERIFIED"

        resolve = await client.post(
            f"/api/v1/reconciliation/records/{rec_id}/resolve-conflict",
            json={"chosen_settlement_id": "DISMISS", "note": "unlink"},
        )
        assert resolve.status_code == 200
        data = await _verify_api(client)
        assert data["status"] == "VERIFIED"
        assert data["tampered"] is False
        assert data["total_records"] >= 15


@pytest.mark.asyncio
async def test_manual_action_then_sql_edit_is_still_caught(db_session: AsyncSession):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        records = await _api_batch(client)
        rec_id = records[0]["id"]
        await client.post(f"/api/v1/reconciliation/records/{rec_id}/approve", json={"note": "ok"})

        await db_session.execute(
            text("UPDATE reconciliation_logs SET diagnostic_note = 'silently changed' WHERE id = :id"), {"id": rec_id}
        )
        await db_session.commit()

        data = await _verify_api(client)
        assert data["status"] == "COMPROMISED"
        assert data["tampered"] is True
        assert data["failed_at_id"] == rec_id
        assert data["expected_hash"] and data["actual_hash"] and data["expected_hash"] != data["actual_hash"]


@pytest.mark.asyncio
async def test_batch_approve_reseals_rows(db_session: AsyncSession):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _api_batch(client)
        resp = await client.post("/api/v1/reconciliation/default/batch-approve", json={"min_confidence": 0.0})
        assert resp.status_code == 200
        assert resp.json()["data"]["approved_count"] > 0
        assert (await _verify_api(client))["status"] == "VERIFIED"


@pytest.mark.asyncio
async def test_verify_endpoint_reports_modified_row(db_session: AsyncSession):
    await _seed_and_reconcile(db_session)
    victim = (
        (await db_session.execute(select(ReconciliationLog).order_by(ReconciliationLog.created_at))).scalars().all()[3]
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await _verify_api(client, BATCH))["status"] == "VERIFIED"
        await db_session.execute(
            text("UPDATE reconciliation_logs SET delta_amount = 1.00 WHERE id = :id"), {"id": victim.id}
        )
        await db_session.commit()
        data = await _verify_api(client, BATCH)
    assert data["status"] == "COMPROMISED"
    assert data["tampered"] is True
    assert data["failed_at_id"] == victim.id


# --- certificate ---


@pytest.mark.asyncio
async def test_certificate_signed_with_hmac(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "AUDIT_SIGNING_KEY", "unit-test-key")
    await _seed_and_reconcile(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/v1/reconciliation/{BATCH}/audit-certificate")
    assert resp.status_code == 200
    assert "attachment" in resp.headers["content-disposition"]
    cert = resp.json()
    assert cert["batch_id"] == BATCH
    assert cert["verification"]["status"] == "VERIFIED"
    assert cert["signed"] is True and cert["signature_algorithm"] == "HMAC-SHA256"

    body = {k: v for k, v in cert.items() if k not in {"content_sha256", "signed", "signature_algorithm", "signature"}}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    assert cert["content_sha256"] == hashlib.sha256(canonical).hexdigest()
    assert cert["signature"] == hmac.new(b"unit-test-key", canonical, hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_certificate_without_key_is_unsigned(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "AUDIT_SIGNING_KEY", "")
    await _seed_and_reconcile(db_session)
    result = await _verify(db_session)
    cert = build_audit_certificate(BATCH, result, settings.AUDIT_SIGNING_KEY)
    assert cert["signed"] is False
    assert cert["signature"] is None
    assert len(cert["content_sha256"]) == 64


@pytest.mark.asyncio
async def test_certificate_reports_compromised_batch(db_session: AsyncSession):
    _, _, logs = await _seed_and_reconcile(db_session)
    await db_session.execute(
        text("UPDATE reconciliation_logs SET match_status = 'MATCHED' WHERE id = :id"), {"id": logs[-1].id}
    )
    await db_session.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        cert = (await client.get(f"/api/v1/reconciliation/{BATCH}/audit-certificate")).json()
    assert cert["verification"]["status"] == "COMPROMISED"
    assert cert["verification"]["failed_at_id"] == logs[-1].id


# --- migration backfill ---


def test_migration_backfills_existing_rows_into_a_valid_chain(tmp_path, monkeypatch: pytest.MonkeyPatch):
    from alembic.config import Config

    from alembic import command
    from app.services.reconciliation import verify_chain

    db_file = tmp_path / "legacy.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_file}")
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    cfg = Config(os.path.join(backend_dir, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))

    command.upgrade(cfg, "0001")
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute(
        "INSERT INTO bank_transactions (id, created_at, updated_at, batch_id, row_hash, date, amount, direction, "
        "description, raw_csv_row) VALUES ('b1','2026-01-01 00:00:00','2026-01-01 00:00:00','legacy','h1',"
        "'2026-01-01 00:00:00',100.00,'CREDIT','x','{}')"
    )
    for i, batch in enumerate(["legacy", "legacy", "legacy", "other"]):
        conn.execute(
            "INSERT INTO reconciliation_logs (id, created_at, updated_at, batch_id, bank_tx_id, match_status, "
            "match_tier, confidence_score, delta_amount, diagnostic_type, diagnostic_note, matched_at, superseded) "
            "VALUES (?, '2026-01-01 10:00:00.000000', '2026-01-01 10:00:00.000000', ?, 'b1', 'MATCHED', 'TIER_1', "
            "1.0, 12.50, 'EXACT_MATCH', 'legacy note', '2026-01-01 10:00:00.000000', 0)",
            (f"legacy-log-{i}", batch),
        )
    conn.commit()
    conn.close()

    command.upgrade(cfg, "0002")

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(f"sqlite:///{db_file}")
    with Session(engine) as session:
        for batch, expected in (("legacy", 3), ("other", 1)):
            rows = (
                session.execute(
                    select(ReconciliationLog)
                    .where(ReconciliationLog.batch_id == batch)
                    .order_by(ReconciliationLog.created_at, ReconciliationLog.id)
                )
                .scalars()
                .all()
            )
            assert len(rows) == expected
            result = verify_chain(rows)
            assert result.status == "VERIFIED", result
            assert rows[0].previous_hash is None

        # new rows added after the migration extend the legacy chain
        session.add(
            ReconciliationLog(bank_tx_id="b1", batch_id="legacy", match_status="EXCEPTION", match_tier="TIER_3")
        )
        session.commit()
        rows = (
            session.execute(
                select(ReconciliationLog)
                .where(ReconciliationLog.batch_id == "legacy")
                .order_by(ReconciliationLog.created_at, ReconciliationLog.id)
            )
            .scalars()
            .all()
        )
        assert len(rows) == 4
        assert verify_chain(rows).status == "VERIFIED"
    engine.dispose()

    command.downgrade(cfg, "0001")
