"""Excel export: three tabs, literal text cells, currency format, SUM formulas, frozen header."""

import io
from datetime import UTC, datetime
from decimal import Decimal

from httpx import ASGITransport, AsyncClient
from openpyxl import load_workbook

from app.main import app
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.models.reconciliation_log import ReconciliationLog


def _log(batch, key, utr, setl, status, amount="100.00"):
    bank = BankTransaction(
        batch_id=batch,
        row_hash=key,
        date=datetime(2026, 1, 1, tzinfo=UTC),
        amount=Decimal(amount),
        direction="CREDIT",
        description="CMS",
        utr=utr,
    )
    rzp = RazorpaySettlement(
        settlement_id=setl,
        amount=Decimal(amount),
        gross_amount=Decimal("102.36"),
        fees=Decimal("2.00"),
        tax=Decimal("0.36"),
    )
    return ReconciliationLog(
        batch_id=batch,
        bank_transaction=bank,
        rzp_settlement=rzp,
        match_status=status,
        match_tier="TIER_1",
        delta_amount=Decimal("0.00") if status == "MATCHED" else Decimal("5.00"),
        diagnostic_note="note",
    )


async def test_xlsx_export(db_session):
    db_session.add(_log("xl", "r1", "982100000012345", "setl_1", "MATCHED"))
    db_session.add(_log("xl", "r2", "=1+2", "setl_2", "EXCEPTION", "90.00"))
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/reconciliation/xl/export-xlsx")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/vnd.openxmlformats")

    wb = load_workbook(io.BytesIO(response.content))
    assert wb.sheetnames == ["Executive Summary", "Reconciled Ledger", "Exceptions & Discrepancies"]

    ledger = wb["Reconciled Ledger"]
    assert ledger.freeze_panes == "A2"
    assert ledger["B2"].value == "982100000012345"
    assert ledger["B2"].data_type == "s"
    assert "#,##0.00" in ledger["D2"].number_format
    assert ledger["D4"].value == "=SUM(D2:D2)"

    exceptions = wb["Exceptions & Discrepancies"]
    assert exceptions["B2"].value == "=1+2"
    assert exceptions["B2"].data_type == "s"
    assert exceptions["F4"].value == "=SUM(F2:F2)"
