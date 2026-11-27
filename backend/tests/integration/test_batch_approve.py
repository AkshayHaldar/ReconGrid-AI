"""Atomic batch approval protects the threshold and batch boundary."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.models.reconciliation_log import ReconciliationLog


@pytest.mark.asyncio
async def test_batch_approve_only_updates_eligible_active_suggestions(db_session: AsyncSession):
    candidates = [
        ("target", "SUGGESTED", 0.95, False),
        ("target", "SUGGESTED", 0.90, False),
        ("target", "SUGGESTED", 0.89, False),
        ("target", "MATCHED", 0.99, False),
        ("target", "SUGGESTED", 0.99, True),
        ("other", "SUGGESTED", 0.99, False),
        ("target", "SUGGESTED", 0.98, False),
        ("target", "SUGGESTED", 0.89, False),
    ]
    settlement = RazorpaySettlement(id="competing-payout", settlement_id="setl_competing", amount=Decimal("100.00"))
    db_session.add(settlement)
    logs = []
    for index, (batch_id, match_status, confidence, superseded) in enumerate(candidates):
        bank = BankTransaction(
            id=f"bank-{index}",
            batch_id=batch_id,
            row_hash=f"hash-{index}",
            date=datetime(2026, 11, 16, tzinfo=UTC),
            amount=Decimal("100.00"),
            direction="CREDIT",
            description="Batch approval test",
        )
        log = ReconciliationLog(
            id=f"log-{index}",
            bank_tx_id=bank.id,
            batch_id=batch_id,
            rzp_settlement_id=settlement.id if index >= 6 else None,
            match_status=match_status,
            match_tier="TIER_2",
            confidence_score=confidence,
            diagnostic_type="FUZZY_MATCH",
            diagnostic_note="Candidate",
            superseded=superseded,
        )
        db_session.add_all((bank, log))
        logs.append(log)
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/reconciliation/target/batch-approve", json={"min_confidence": 0.90})
        assert response.status_code == 200
        assert response.json()["data"] == {"approved_count": 2, "batch_id": "target"}
        repeat = await client.post("/api/v1/reconciliation/target/batch-approve", json={"min_confidence": 0.90})
        assert repeat.json()["data"]["approved_count"] == 0
        assert (
            await client.post("/api/v1/reconciliation/target/batch-approve", json={"min_confidence": 1.1})
        ).status_code == 422
        assert (await client.post("/api/v1/reconciliation/records/log-6/approve", json={})).status_code == 409

    for log in logs:
        await db_session.refresh(log)
    for log in logs[:2]:
        assert log.match_status == "SUGGESTED" and log.human_action is None
        assert log.superseded and log.diagnostic_note == "Candidate"
        successor = await db_session.get(ReconciliationLog, log.superseded_by_id)
        assert successor is not None and not successor.superseded
        assert successor.match_status == "MATCHED" and successor.human_action == "APPROVED"
        assert successor.diagnostic_note == "Candidate [Batch Approved >= 90% by CA]"
    for log, (_, status, _, _) in zip(logs[2:], candidates[2:]):
        assert log.match_status == status
        assert log.diagnostic_note == "Candidate"
