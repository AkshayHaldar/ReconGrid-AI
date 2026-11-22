from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.bank_transaction import BankTransaction
from app.models.reconciliation_log import ReconciliationLog


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_date_range_filtering_and_ist_midnight_boundaries(db_session, client):
    # Transaction 1: 31 March 2026, 18:00:00 UTC -> 31 March 2026, 23:30:00 IST (Q4 FY 25-26)
    tx_q4 = BankTransaction(
        id=str(UUID(int=1)),
        batch_id="test_dates",
        row_hash="hash-1",
        date=datetime(2026, 3, 31, 18, 0, 0, tzinfo=UTC),
        amount=Decimal("1000.00"),
        description="March 31 late transaction",
    )
    log_q4 = ReconciliationLog(
        id=str(UUID(int=101)),
        bank_transaction=tx_q4,
        batch_id="test_dates",
        match_status="MATCHED",
        match_tier="TIER_1",
        diagnostic_type="EXACT_MATCH",
    )

    # Transaction 2: 31 March 2026, 19:00:00 UTC -> 1 April 2026, 00:30:00 IST (Q1 FY 26-27)
    tx_q1_start = BankTransaction(
        id=str(UUID(int=2)),
        batch_id="test_dates",
        row_hash="hash-2",
        date=datetime(2026, 3, 31, 19, 0, 0, tzinfo=UTC),
        amount=Decimal("2000.00"),
        description="April 1 early transaction",
    )
    log_q1_start = ReconciliationLog(
        id=str(UUID(int=102)),
        bank_transaction=tx_q1_start,
        batch_id="test_dates",
        match_status="MATCHED",
        match_tier="TIER_1",
        diagnostic_type="EXACT_MATCH",
    )

    # Transaction 3: 15 May 2026, 10:00:00 UTC -> Q1 FY 26-27
    tx_q1_mid = BankTransaction(
        id=str(UUID(int=3)),
        batch_id="test_dates",
        row_hash="hash-3",
        date=datetime(2026, 5, 15, 10, 0, 0, tzinfo=UTC),
        amount=Decimal("3000.00"),
        description="May 15 transaction",
    )
    log_q1_mid = ReconciliationLog(
        id=str(UUID(int=103)),
        bank_transaction=tx_q1_mid,
        batch_id="test_dates",
        match_status="MATCHED",
        match_tier="TIER_1",
        diagnostic_type="EXACT_MATCH",
    )

    # Transaction 4: 15 August 2026, 10:00:00 UTC -> Q2 FY 26-27
    tx_q2 = BankTransaction(
        id=str(UUID(int=4)),
        batch_id="test_dates",
        row_hash="hash-4",
        date=datetime(2026, 8, 15, 10, 0, 0, tzinfo=UTC),
        amount=Decimal("4000.00"),
        description="August 15 transaction",
    )
    log_q2 = ReconciliationLog(
        id=str(UUID(int=104)),
        bank_transaction=tx_q2,
        batch_id="test_dates",
        match_status="MATCHED",
        match_tier="TIER_1",
        diagnostic_type="EXACT_MATCH",
    )

    db_session.add_all([tx_q4, log_q4, tx_q1_start, log_q1_start, tx_q1_mid, log_q1_mid, tx_q2, log_q2])
    await db_session.commit()

    # Query without date range -> all 4 records
    res_all = await client.get("/api/v1/reconciliation/test_dates/records?limit=10")
    assert res_all.status_code == 200
    assert len(res_all.json()["data"]["records"]) == 4

    # Query for Q1 FY 26-27 (2026-04-01 to 2026-06-30 in IST)
    # Should include tx_q1_start (00:30 IST April 1) and tx_q1_mid, but exclude tx_q4 and tx_q2!
    res_q1 = await client.get(
        "/api/v1/reconciliation/test_dates/records",
        params={"limit": 10, "from_date": "2026-04-01", "to_date": "2026-06-30"},
    )
    assert res_q1.status_code == 200
    records_q1 = res_q1.json()["data"]["records"]
    assert len(records_q1) == 2
    record_ids_q1 = {r["id"] for r in records_q1}
    assert record_ids_q1 == {log_q1_start.id, log_q1_mid.id}

    # Query for Q4 FY 25-26 (2026-01-01 to 2026-03-31 in IST)
    # Should include tx_q4 (23:30 IST March 31)
    res_q4 = await client.get(
        "/api/v1/reconciliation/test_dates/records",
        params={"limit": 10, "from_date": "2026-01-01", "to_date": "2026-03-31"},
    )
    assert res_q4.status_code == 200
    records_q4 = res_q4.json()["data"]["records"]
    assert len(records_q4) == 1
    assert records_q4[0]["id"] == log_q4.id

    # Legacy pagination mode with from_date & to_date
    res_legacy = await client.get(
        "/api/v1/reconciliation/test_dates/records",
        params={"page": 1, "page_size": 10, "from_date": "2026-04-01", "to_date": "2026-06-30"},
    )
    assert res_legacy.status_code == 200
    assert len(res_legacy.json()["data"]["records"]) == 2
