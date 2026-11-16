"""Export text stays literal without changing stored data or numeric cells."""

import csv
import io
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.models.reconciliation_log import ReconciliationLog


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("=1+2", "'=1+2"),
        ("+1+2", "'+1+2"),
        ("-1+2", "'-1+2"),
        ("@SUM(1,2)", "'@SUM(1,2)"),
        ("\t=1+2", "'\t=1+2"),
        ("\r=1+2", "'\r=1+2"),
        ("\n=1+2", "'\n=1+2"),
        ("  =1+2", "'  =1+2"),
        ("\ufeff=1+2", "'\ufeff=1+2"),
        ("Invoice 42", "Invoice 42"),
        ('Invoice, "quoted"\nsecond line', 'Invoice, "quoted"\nsecond line'),
        ("", ""),
    ],
)
async def test_export_neutralizes_text_cells_but_preserves_amounts(db_session, text, expected):
    bank = BankTransaction(
        batch_id="csv-safety",
        row_hash="synthetic-csv-row",
        date=datetime(2026, 1, 1, tzinfo=UTC),
        amount=Decimal("-10.25"),
        direction="DEBIT",
        description=text,
        utr=text,
    )
    settlement = RazorpaySettlement(settlement_id=text, amount=Decimal("12.50"))
    log = ReconciliationLog(
        batch_id="csv-safety",
        bank_transaction=bank,
        rzp_settlement=settlement,
        match_status="EXCEPTION",
        match_tier="TIER_1",
        diagnostic_note=text,
    )
    db_session.add(log)
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/reconciliation/csv-safety/export")
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.text, newline="")))
    assert len(rows) == 1
    for column in ("Bank Description", "Bank UTR", "Razorpay Settlement ID", "Diagnostic Note"):
        assert rows[0][column] == expected
    assert rows[0]["Bank Amount (INR)"] == "-10.25"
    assert rows[0]["Razorpay Net (INR)"] == "12.50"
    assert rows[0]["Direction"] == "DEBIT"
    assert rows[0]["Date"] == "2026-01-01"
    await db_session.refresh(bank)
    await db_session.refresh(log)
    assert bank.description == bank.utr == log.diagnostic_note == text
