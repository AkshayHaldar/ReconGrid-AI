"""Month-end close: pre-flight checks, sign-off record and the HTTP 423 ledger freeze."""

import asyncio
import hashlib
import hmac
import json
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.v1 import webhooks
from app.core.config import settings
from app.main import app
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.models.reconciliation_log import ReconciliationBatch, ReconciliationLog
from app.models.webhook_event import ProcessedWebhookEvent
from app.repositories.reconciliation_repo import ReconciliationRepository
from app.repositories.settlement_repo import SettlementRepository
from app.schemas.razorpay import RazorpayRefundPayload
from app.services.batch_lock import BatchLockedError, ensure_batch_unlocked, lock_batch
from app.services.reconciliation import ReconciliationEngine

API = "/api/v1/reconciliation"
SIGN_OFF = {"locked_by": "CA Ramesh, Partner at ABC & Co.", "lock_note": "Audited & Approved"}


async def add_log(db: AsyncSession, batch_id: str, name: str, match_status: str, human_action=None, amount="100.00"):
    bank = BankTransaction(
        id=f"bank-{name}",
        batch_id=batch_id,
        row_hash=f"hash-{name}",
        date=datetime(2026, 8, 20, tzinfo=UTC),
        amount=Decimal(amount),
        direction="CREDIT",
        description=f"Test {name}",
    )
    log = ReconciliationLog(
        id=f"log-{name}",
        bank_tx_id=bank.id,
        batch_id=batch_id,
        match_status=match_status,
        match_tier="TIER_1",
        confidence_score=0.95,
        diagnostic_type="EXACT_MATCH",
        diagnostic_note="seed",
        human_action=human_action,
    )
    db.add_all((bank, log))
    await db.commit()
    return log


async def reload(db: AsyncSession, log_id: str) -> ReconciliationLog:
    db.expire_all()
    return await db.get(ReconciliationLog, log_id)


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_lock_rejected_with_unresolved_conflict(db_session, client):
    await add_log(db_session, "aug", "ok", "MATCHED")
    await add_log(db_session, "aug", "conflict", "CONFLICT")

    resp = await client.post(f"{API}/aug/lock", json=SIGN_OFF)

    assert resp.status_code == 422
    error = resp.json()["error"]
    assert error["code"] == "PREFLIGHT_FAILED"
    assert "1 unresolved CONFLICT" in error["message"]
    failed_ids = {c["id"] for c in error["details"]}
    assert "NO_CONFLICTS" in failed_ids
    assert "TRIAL_BALANCE" in failed_ids
    assert await db_session.get(ReconciliationBatch, "aug") is None


@pytest.mark.asyncio
async def test_lock_rejected_with_pending_settlement_data(db_session, client):
    await add_log(db_session, "aug", "ok", "MATCHED")
    await add_log(db_session, "aug", "pending", "PENDING_SETTLEMENT_DATA")

    resp = await client.post(f"{API}/aug/lock", json=SIGN_OFF)

    assert resp.status_code == 422
    failed_ids = {c["id"] for c in resp.json()["error"]["details"]}
    assert "NO_PENDING_SETTLEMENT" in failed_ids
    assert "NO_CONFLICTS" not in failed_ids


@pytest.mark.asyncio
async def test_lock_rejected_when_trial_balance_is_off(db_session, client):
    await add_log(db_session, "aug", "ok", "MATCHED", amount="500.00")
    await add_log(db_session, "aug", "exc", "EXCEPTION", amount="75.50")

    resp = await client.post(f"{API}/aug/lock", json=SIGN_OFF)

    assert resp.status_code == 422
    failed = {c["id"]: c for c in resp.json()["error"]["details"]}
    assert set(failed) == {"TRIAL_BALANCE"}
    assert "75.50" in failed["TRIAL_BALANCE"]["detail"]


@pytest.mark.asyncio
async def test_empty_batch_cannot_be_locked(client):
    resp = await client.post(f"{API}/nothing-here/lock", json=SIGN_OFF)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "PREFLIGHT_FAILED"


@pytest.mark.asyncio
async def test_lock_requires_a_signer_name(db_session, client):
    await add_log(db_session, "aug", "ok", "MATCHED")
    for body in ({}, {"locked_by": "   "}, {"locked_by": "x"}):
        resp = await client.post(f"{API}/aug/lock", json=body)
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert await db_session.get(ReconciliationBatch, "aug") is None


@pytest.mark.asyncio
async def test_preflight_endpoint_reports_checklist_before_locking(db_session, client):
    await add_log(db_session, "aug", "ok", "MATCHED")
    await add_log(db_session, "aug", "conflict", "CONFLICT")

    data = (await client.get(f"{API}/aug/lock")).json()["data"]

    assert data["is_locked"] is False
    assert data["preflight"]["can_lock"] is False
    checks = {c["id"]: c["passed"] for c in data["preflight"]["checks"]}
    assert checks == {"NO_CONFLICTS": False, "NO_PENDING_SETTLEMENT": True, "TRIAL_BALANCE": False}
    assert data["preflight"]["unresolved_variance"] == "100.00"


@pytest.mark.asyncio
async def test_successful_lock_stores_signoff_and_closing_totals(db_session, client):
    await add_log(db_session, "aug", "a", "MATCHED", amount="250.00")
    await add_log(db_session, "aug", "b", "SUGGESTED", human_action="APPROVED", amount="50.25")
    await add_log(db_session, "aug", "c", "CONFLICT", human_action="RESOLVED", amount="10.00")

    resp = await client.post(f"{API}/aug/lock", json=SIGN_OFF)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["is_locked"] is True
    assert data["locked_by"] == SIGN_OFF["locked_by"]
    assert data["lock_note"] == "Audited & Approved"
    assert data["locked_at"] is not None
    assert data["closing_totals"]["total_records"] == 3
    assert data["closing_totals"]["matched_count"] == 3
    assert data["closing_totals"]["total_reconciled_amount"] == "310.25"
    assert data["closing_totals"]["total_unresolved_variance"] == "0.00"

    row = await db_session.get(ReconciliationBatch, "aug")
    assert row.is_locked is True
    assert row.locked_at is not None
    assert row.locked_by == SIGN_OFF["locked_by"]

    # The sign-off is visible on the normal status call the dashboard already polls...
    status = (await client.get(f"{API}/aug/status")).json()["data"]
    assert status["is_locked"] is True
    assert status["locked_by"] == SIGN_OFF["locked_by"]
    # ...and through the lock endpoint, without a pre-flight block.
    again = (await client.get(f"{API}/aug/lock")).json()["data"]
    assert again["is_locked"] is True
    assert again["preflight"] is None

    # An unrelated batch is untouched.
    other = (await client.get(f"{API}/july/status")).json()["data"]
    assert other["is_locked"] is False


@pytest.mark.asyncio
async def test_locking_twice_returns_conflict_and_keeps_first_signoff(db_session, client):
    await add_log(db_session, "aug", "a", "MATCHED")
    assert (await client.post(f"{API}/aug/lock", json=SIGN_OFF)).status_code == 200

    second = await client.post(f"{API}/aug/lock", json={"locked_by": "Somebody Else"})

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "BATCH_ALREADY_LOCKED"
    row = await db_session.get(ReconciliationBatch, "aug")
    assert row.locked_by == SIGN_OFF["locked_by"]


@pytest.mark.asyncio
async def test_writes_return_423_once_locked_and_leave_records_unchanged(db_session, client):
    await add_log(db_session, "aug", "ok", "MATCHED")
    assert (await client.post(f"{API}/aug/lock", json=SIGN_OFF)).status_code == 200
    # A late row slips into the locked batch (e.g. written around the API) and must still be untouchable.
    await add_log(db_session, "aug", "late-sug", "SUGGESTED")
    await add_log(db_session, "aug", "late-deny", "SUGGESTED")
    await add_log(db_session, "aug", "late-conf", "CONFLICT")

    approve = await client.post(f"{API}/records/log-late-sug/approve", json={})
    deny = await client.post(f"{API}/records/log-late-deny/deny", json={})
    resolve = await client.post(f"{API}/records/log-late-conf/resolve-conflict", json={"chosen_settlement_id": "NONE"})
    batch_approve = await client.post(f"{API}/aug/batch-approve", json={"min_confidence": 0.5})
    # Undo of an earlier decision is a write too. The guard runs before the "was it approved" check.
    revert = await client.post(f"{API}/records/log-ok/revert", json={})

    for resp in (approve, deny, resolve, batch_approve, revert):
        assert resp.status_code == 423
        assert resp.json()["error"]["code"] == "BATCH_LOCKED"
        assert resp.json()["error"]["details"]["locked_by"] == SIGN_OFF["locked_by"]

    assert (await reload(db_session, "log-late-sug")).match_status == "SUGGESTED"
    assert (await reload(db_session, "log-late-sug")).human_action is None
    assert (await reload(db_session, "log-late-deny")).match_status == "SUGGESTED"
    assert (await reload(db_session, "log-late-conf")).match_status == "CONFLICT"


@pytest.mark.asyncio
async def test_open_batches_and_unknown_records_behave_as_before(db_session, client):
    await add_log(db_session, "aug", "ok", "MATCHED")
    await add_log(db_session, "sep", "sug", "SUGGESTED")
    assert (await client.post(f"{API}/aug/lock", json=SIGN_OFF)).status_code == 200

    approve = await client.post(f"{API}/records/log-sug/approve", json={})
    assert approve.status_code == 200
    assert approve.json()["data"]["match_status"] == "MATCHED"

    missing = await client.post(f"{API}/records/does-not-exist/approve", json={})
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_statement_upload_to_locked_batch_is_rejected(db_session, client):
    await add_log(db_session, "aug", "ok", "MATCHED")
    assert (await client.post(f"{API}/aug/lock", json=SIGN_OFF)).status_code == 200
    csv_body = b"Date,Description,Credit,Debit\n2026-08-21,UPI/CMS1234567890/RAZORPAY,5000.00,\n"

    resp = await client.post(
        "/api/v1/bank/upload",
        data={"batch_id": "aug"},
        files={"file": ("stmt.csv", csv_body, "text/csv")},
    )

    assert resp.status_code == 423
    assert resp.json()["error"]["code"] == "BATCH_LOCKED"
    count = await db_session.scalar(select(func.count()).select_from(BankTransaction))
    assert count == 1  # only the seeded row


@pytest.mark.asyncio
async def test_reconciliation_engine_refuses_locked_batch(db_session):
    await add_log(db_session, "aug", "ok", "MATCHED")
    repo = ReconciliationRepository(db_session)
    await lock_batch(repo, "aug", "CA Ramesh", None)
    await db_session.commit()

    with pytest.raises(BatchLockedError) as exc:
        await ReconciliationEngine(repo).reconcile_batch([], [], batch_id="aug")
    assert exc.value.status_code == 423
    # Other batches still reconcile.
    assert await ReconciliationEngine(repo).reconcile_batch([], [], batch_id="sep") == []


@pytest.mark.asyncio
async def test_late_webhook_stores_settlement_but_does_not_rematch_locked_batch(db_session, monkeypatch):
    await add_log(db_session, "default", "ok", "MATCHED")
    await lock_batch(ReconciliationRepository(db_session), "default", "CA Ramesh", None)
    await db_session.commit()
    monkeypatch.setattr(webhooks.BankRepository, "get_all_by_batch", AsyncMock(return_value=[object()]))
    payload = {
        "id": "evt_late",
        "event": "settlement.processed",
        "payload": {"settlement": {"entity": {"id": "setl_late", "amount": 10000, "fees": 100, "tax": 18}}},
    }
    body = json.dumps(payload).encode()
    sig = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/webhooks/razorpay",
            content=body,
            headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
        )

    assert resp.status_code == 200
    db_session.expire_all()
    assert await db_session.scalar(select(func.count()).select_from(RazorpaySettlement)) == 1
    status = await db_session.scalar(
        select(ProcessedWebhookEvent.processing_status).where(ProcessedWebhookEvent.razorpay_event_id == "evt_late")
    )
    assert status == "PROCESSED"
    # The ledger rows of the locked batch were not superseded or rewritten.
    logs = (await db_session.scalars(select(ReconciliationLog))).all()
    assert [(l.id, l.superseded) for l in logs] == [("log-ok", False)]


@pytest.mark.asyncio
async def test_refund_webhook_skips_locked_batch_and_still_rematches_open_one(db_session, client):
    settlement = RazorpaySettlement(id="setl-db", settlement_id="setl_shared", amount=Decimal("100.00"))
    db_session.add(settlement)
    for batch_id, name in (("aug", "closed"), ("sep", "open")):
        log = await add_log(db_session, batch_id, name, "MATCHED")
        log.rzp_settlement_id = settlement.id
    db_session.add(ReconciliationBatch(batch_id="aug", is_locked=True, locked_by="CA Ramesh"))
    await db_session.commit()
    payload = {
        "id": "evt_refund_late",
        "event": "refund.processed",
        "payload": {
            "refund": {
                "entity": {
                    "id": "rfnd_late",
                    "payment_id": "pay_late",
                    "currency": "INR",
                    "amount": 500,
                    "status": "processed",
                    "created_at": 1787200000,
                }
            }
        },
    }
    await SettlementRepository(db_session).upsert_refund(
        RazorpayRefundPayload.model_validate(payload["payload"]["refund"]["entity"]).to_record({})
    )
    await SettlementRepository(db_session).link_refund("rfnd_late", "setl_shared")
    await db_session.commit()
    body = json.dumps(payload).encode()
    sig = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()

    resp = await client.post(
        "/api/v1/webhooks/razorpay",
        content=body,
        headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
    )

    assert resp.status_code == 200
    db_session.expire_all()
    status = await db_session.scalar(
        select(ProcessedWebhookEvent.processing_status).where(
            ProcessedWebhookEvent.razorpay_event_id == "evt_refund_late"
        )
    )
    assert status == "PROCESSED"
    closed = (await db_session.scalars(select(ReconciliationLog).where(ReconciliationLog.batch_id == "aug"))).all()
    assert [(log.id, log.superseded) for log in closed] == [("log-closed", False)]
    reopened = (await db_session.scalars(select(ReconciliationLog).where(ReconciliationLog.batch_id == "sep"))).all()
    assert len(reopened) == 2
    assert [log.id for log in reopened if log.superseded] == ["log-open"]


async def add_settled_log(db: AsyncSession, batch_id: str, name: str, settlement_id: str):
    settlement = RazorpaySettlement(
        id=f"db-{settlement_id}",
        settlement_id=settlement_id,
        amount=Decimal("100.00"),
        gross_amount=Decimal("100.00"),
        utr=f"UTR-{name}",
        is_test_mode=True,
    )
    db.add(settlement)
    log = await add_log(db, batch_id, name, "MATCHED")
    log.rzp_settlement_id = settlement.id
    await db.commit()
    return settlement


def settlement_update(settlement_id: str) -> dict:
    return {"settlement_id": settlement_id, "amount": Decimal("999.00"), "utr": "CHANGED"}


@pytest.mark.asyncio
async def test_settlement_shown_by_a_locked_batch_is_not_updated(db_session, client):
    await add_settled_log(db_session, "aug", "closed", "setl_closed")
    await add_settled_log(db_session, "sep", "open", "setl_open")
    assert (await client.post(f"{API}/aug/lock", json=SIGN_OFF)).status_code == 200
    repo = SettlementRepository(db_session)

    closed, closed_flag = await repo.upsert_settlement(settlement_update("setl_closed"))
    opened, opened_flag = await repo.upsert_settlement(settlement_update("setl_open"))

    assert (closed_flag, closed.amount, closed.utr) == (None, Decimal("100.00"), "UTR-closed")
    assert (opened_flag, opened.amount, opened.utr) == (False, Decimal("999.00"), "CHANGED")


@pytest.mark.asyncio
async def test_demo_reset_keeps_settlements_of_a_locked_batch(db_session, client):
    await add_settled_log(db_session, "aug", "closed", "setl_closed")
    await add_settled_log(db_session, "sep", "open", "setl_open")
    assert (await client.post(f"{API}/aug/lock", json=SIGN_OFF)).status_code == 200

    assert (await client.post("/api/v1/demo/reset", params={"batch_id": "sep"})).status_code == 200

    db_session.expire_all()
    assert (await db_session.scalars(select(RazorpaySettlement.settlement_id))).all() == ["setl_closed"]


@pytest.mark.asyncio
async def test_refund_after_sign_off_leaves_the_locked_tax_schedule_alone(db_session, client):
    await add_settled_log(db_session, "aug", "closed", "setl_closed")
    assert (await client.post(f"{API}/aug/lock", json=SIGN_OFF)).status_code == 200
    before = (await client.get(f"{API}/aug/tax-schedule")).json()["data"]

    entity = {
        "id": "rfnd_after",
        "payment_id": "pay_after",
        "currency": "INR",
        "amount": 2500,
        "status": "processed",
        "created_at": 1787200000,
    }
    repo = SettlementRepository(db_session)
    await repo.upsert_refund(RazorpayRefundPayload.model_validate(entity).to_record(entity))
    await repo.link_refund("rfnd_after", "setl_closed")
    await db_session.commit()

    assert (await client.get(f"{API}/aug/tax-schedule")).json()["data"] == before
    # The refund itself is still stored.
    assert await repo.get_processed_refund_totals({"setl_closed"}) == {"setl_closed": Decimal("25.00")}


@pytest.mark.asyncio
async def test_postgres_sign_off_waits_for_an_in_flight_ledger_write(db_session):
    if db_session.get_bind().dialect.name != "postgresql":
        pytest.skip("needs real concurrent transactions")
    await add_log(db_session, "aug", "ok", "MATCHED")
    sessions = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    async with sessions() as writer, sessions() as signer:
        await ensure_batch_unlocked(ReconciliationRepository(writer), "aug")
        sign_off = asyncio.create_task(lock_batch(ReconciliationRepository(signer), "aug", "CA Ramesh", None))
        await asyncio.sleep(0.5)
        assert not sign_off.done()
        # The writer commits a conflict while the sign-off is queued; the sign-off must see it.
        await add_log(writer, "aug", "conflict", "CONFLICT")
        with pytest.raises(HTTPException) as exc:
            await asyncio.wait_for(sign_off, 5)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_postgres_writer_queued_behind_a_sign_off_is_refused(db_session):
    if db_session.get_bind().dialect.name != "postgresql":
        pytest.skip("needs real concurrent transactions")
    await add_log(db_session, "aug", "ok", "MATCHED")
    sessions = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    async with sessions() as writer, sessions() as signer:
        await lock_batch(ReconciliationRepository(signer), "aug", "CA Ramesh", None)
        write = asyncio.create_task(ensure_batch_unlocked(ReconciliationRepository(writer), "aug"))
        await asyncio.sleep(0.5)
        assert not write.done()
        await signer.commit()
        with pytest.raises(BatchLockedError):
            await asyncio.wait_for(write, 5)


@pytest.mark.asyncio
async def test_postgres_sign_off_waits_for_an_in_flight_settlement_write(db_session):
    if db_session.get_bind().dialect.name != "postgresql":
        pytest.skip("needs real concurrent transactions")
    await add_settled_log(db_session, "aug", "closed", "setl_closed")
    sessions = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    async with sessions() as writer, sessions() as signer:
        await SettlementRepository(writer).upsert_settlement(settlement_update("setl_closed"))
        sign_off = asyncio.create_task(lock_batch(ReconciliationRepository(signer), "aug", "CA Ramesh", None))
        await asyncio.sleep(0.5)
        assert not sign_off.done()
        await writer.commit()
        await asyncio.wait_for(sign_off, 5)
        await signer.commit()


def test_alembic_0003_creates_and_drops_reconciliation_batches(tmp_path):
    import os
    import sqlite3
    import subprocess
    import sys

    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    db_file = tmp_path / "migrate.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db_file}"}

    def alembic(*args):
        subprocess.run(
            [sys.executable, "-m", "alembic", *args], cwd=backend_dir, env=env, check=True, capture_output=True
        )

    def columns():
        with sqlite3.connect(db_file) as conn:
            return [row[1] for row in conn.execute("PRAGMA table_info(reconciliation_batches)")]

    alembic("upgrade", "head")
    assert columns() == [
        "batch_id",
        "created_at",
        "updated_at",
        "is_locked",
        "locked_at",
        "locked_by",
        "lock_note",
        "closing_totals",
        "refund_snapshot",
    ]
    alembic("downgrade", "0002")
    assert columns() == []
