"""Writers of the same batch_id queue behind one shared lock instead of racing their snapshots."""

import asyncio
import io
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1 import webhooks
from app.main import app
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.models.reconciliation_log import ReconciliationLog
from app.models.webhook_event import ProcessedWebhookEvent

CSV = (
    "Date,Chq/Ref No.,Narration,Deposit Amt.,Withdrawal Amt.\n"
    "24/08/2026,CMS002938491805,CMS/CMS002938491805/RAZORPAY ORDER 4521,49100.00,0.00\n"
)


async def dialect_name() -> str:
    async with webhooks.async_session_factory() as db:
        return db.bind.dialect.name


async def seed(batch_id: str = "default") -> None:
    """A settlement that already existed, a queued webhook event and one SUGGESTED log in the batch."""
    async with webhooks.async_session_factory() as db:
        db.add(
            RazorpaySettlement(
                settlement_id="setl_seed",
                amount=Decimal("100.00"),
                gross_amount=Decimal("102.36"),
                fees=Decimal("2.00"),
                tax=Decimal("0.36"),
                settlement_created_at=datetime(2026, 11, 20, tzinfo=UTC),
                raw_payload={},
            )
        )
        db.add(
            ProcessedWebhookEvent(
                razorpay_event_id="evt_holder",
                event_type="settlement.processed",
                processing_status="QUEUED",
                payload={"payload": {"settlement": {"entity": {"id": "setl_holder", "amount": 10000}}}},
            )
        )
        bank = BankTransaction(
            id="bank-lock",
            batch_id=batch_id,
            row_hash="hash-lock",
            date=datetime(2026, 11, 20, tzinfo=UTC),
            amount=Decimal("100.00"),
            direction="CREDIT",
            description="Lock test",
        )
        db.add_all(
            (
                bank,
                ReconciliationLog(
                    id="log-lock",
                    bank_tx_id=bank.id,
                    batch_id=batch_id,
                    match_status="SUGGESTED",
                    match_tier="TIER_2",
                    confidence_score=0.95,
                    diagnostic_type="FUZZY_MATCH",
                    diagnostic_note="Candidate",
                ),
            )
        )
        await db.commit()


@pytest.fixture
def snapshots(monkeypatch):
    """reconcile_batch records the settlements it was given; the first call (the holder) blocks until released."""
    taken: list[list[str]] = []
    holder_entered, release = asyncio.Event(), asyncio.Event()

    async def fake_reconcile(self, bank_transactions, settlements, batch_id="default"):
        taken.append(sorted(s.settlement_id for s in settlements))
        if len(taken) == 1:
            holder_entered.set()
            await release.wait()
        return []

    monkeypatch.setattr(webhooks.BankRepository, "get_all_by_batch", AsyncMock(return_value=[object()]))
    monkeypatch.setattr(webhooks.ReconciliationEngine, "reconcile_batch", fake_reconcile)
    return taken, holder_entered, release


def contender_request(client: AsyncClient, kind: str):
    if kind == "bank_upload":
        files = {"file": ("statement.csv", io.BytesIO(CSV.encode()), "text/csv")}
        return client.post("/api/v1/bank/upload", data={"batch_id": "default"}, files=files)
    if kind == "razorpay_sync":
        return client.post("/api/v1/razorpay/sync?batch_id=default", json={"count": 10})
    if kind == "batch_approve":
        return client.post("/api/v1/reconciliation/default/batch-approve", json={"min_confidence": 0.9})
    return client.post(f"/api/v1/reconciliation/records/log-lock/{kind}", json={"note": "lock test"})


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["bank_upload", "razorpay_sync", "batch_approve", "approve", "deny"])
async def test_writer_waits_for_webhook_reconcile_on_same_batch(kind, snapshots):
    taken, holder_entered, release = snapshots
    await seed()
    holder = asyncio.create_task(webhooks.reconcile_webhook_event("evt_holder"))
    await asyncio.wait_for(holder_entered.wait(), 5)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        contender = asyncio.create_task(contender_request(client, kind))
        try:
            await asyncio.sleep(0.3)
            # The webhook still holds the batch: the contender has not got past the lock.
            assert not contender.done()
            assert len(taken) == 1
        finally:
            release.set()
        await asyncio.wait_for(holder, 10)
        response = await asyncio.wait_for(contender, 10)

    assert response.status_code == 200, response.text
    if kind in ("bank_upload", "razorpay_sync"):
        # The second snapshot was read after the webhook committed, so it includes the webhook's settlement.
        assert taken == [["setl_holder", "setl_seed"], ["setl_holder", "setl_seed"]]
    else:
        assert taken == [["setl_holder", "setl_seed"]]


@pytest.mark.asyncio
async def test_two_uploads_on_one_batch_do_not_interleave(monkeypatch):
    order: list[str] = []
    first_entered, release = asyncio.Event(), asyncio.Event()

    async def fake_reconcile(self, bank_transactions, settlements, batch_id="default"):
        order.append(f"start:{len(bank_transactions)}")
        if len(order) == 1:
            first_entered.set()
            await release.wait()
        order.append("end")
        return []

    monkeypatch.setattr(webhooks.ReconciliationEngine, "reconcile_batch", fake_reconcile)
    second_csv = CSV + "25/08/2026,CMS002938491806,CMS/CMS002938491806/RAZORPAY ORDER 4522,1200.00,0.00\n"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = asyncio.create_task(
            client.post(
                "/api/v1/bank/upload",
                data={"batch_id": "shared"},
                files={"file": ("a.csv", io.BytesIO(CSV.encode()), "text/csv")},
            )
        )
        await asyncio.wait_for(first_entered.wait(), 5)
        second = asyncio.create_task(
            client.post(
                "/api/v1/bank/upload",
                data={"batch_id": "shared"},
                files={"file": ("b.csv", io.BytesIO(second_csv.encode()), "text/csv")},
            )
        )
        await asyncio.sleep(0.3)
        assert not second.done()
        release.set()
        responses = await asyncio.wait_for(asyncio.gather(first, second), 10)
    assert [r.status_code for r in responses] == [200, 200]
    assert order == ["start:1", "end", "start:2", "end"]
    # The second upload saw the first one's committed row as a duplicate, not a concurrent insert.
    assert responses[1].json()["data"]["duplicate_count"] == 1


@pytest.mark.asyncio
async def test_other_batches_are_not_blocked_on_postgres(snapshots):
    if await dialect_name() != "postgresql":
        pytest.skip("SQLite has a single database-wide writer, so every batch shares its lock")
    taken, holder_entered, release = snapshots
    await seed(batch_id="other")
    holder = asyncio.create_task(webhooks.reconcile_webhook_event("evt_holder"))
    await asyncio.wait_for(holder_entered.wait(), 5)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await asyncio.wait_for(
                client.post("/api/v1/reconciliation/other/batch-approve", json={"min_confidence": 0.9}), 5
            )
        assert response.json()["data"]["approved_count"] == 1
        assert not holder.done()
    finally:
        release.set()
        await asyncio.wait_for(holder, 10)
