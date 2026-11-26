"""Regression coverage ensuring CSV, Excel, and Tally XML exports paginate past 10,000 rows."""

import csv
import io
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from httpx import ASGITransport, AsyncClient
from openpyxl import load_workbook

from app.api.v1 import reconciliation as reconciliation_api
from app.main import app
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.models.reconciliation_log import ReconciliationLog


def _make_db_log(batch_id: str, index: int, status: str = "MATCHED") -> ReconciliationLog:
    tx_date = datetime(2026, 2, 1, tzinfo=UTC) + timedelta(minutes=index)
    amount = Decimal("100.00")
    bank = BankTransaction(
        batch_id=batch_id,
        row_hash=f"{batch_id}-row-{index}",
        date=tx_date,
        amount=amount,
        direction="CREDIT",
        description=f"NEFT/UTR{index:05d}",
        utr=f"UTR{index:05d}",
    )
    rzp = RazorpaySettlement(
        settlement_id=f"setl_{batch_id}_{index:05d}",
        amount=amount,
        gross_amount=Decimal("102.36"),
        fees=Decimal("2.00"),
        tax=Decimal("0.36"),
    )
    return ReconciliationLog(
        batch_id=batch_id,
        bank_transaction=bank,
        rzp_settlement=rzp,
        match_status=status,
        match_tier="TIER_1",
        delta_amount=Decimal("0.00") if status == "MATCHED" else Decimal("5.00"),
        diagnostic_type="EXACT_MATCH" if status == "MATCHED" else "AMOUNT_MISMATCH",
        diagnostic_note=f"row-{index}",
    )


async def test_exports_paginate_all_pages_from_database(db_session, monkeypatch):
    """CSV, XLSX, and Tally XML must traverse all pages instead of stopping at page 1."""
    batch_id = "paginated-db-batch"
    for i in range(5):
        status = "EXCEPTION" if i == 4 else "MATCHED"
        db_session.add(_make_db_log(batch_id, i, status=status))
    await db_session.commit()

    monkeypatch.setattr(reconciliation_api, "EXPORT_PAGE_SIZE", 2)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        csv_resp = await client.get(f"/api/v1/reconciliation/{batch_id}/export")
        xlsx_resp = await client.get(f"/api/v1/reconciliation/{batch_id}/export-xlsx")
        xml_resp = await client.get(f"/api/v1/reconciliation/{batch_id}/export-tally-xml")

    assert csv_resp.status_code == 200
    csv_rows = list(csv.DictReader(io.StringIO(csv_resp.text, newline="")))
    assert len(csv_rows) == 5
    assert {row["Bank UTR"] for row in csv_rows} == {f"UTR{i:05d}" for i in range(5)}

    assert xlsx_resp.status_code == 200
    wb = load_workbook(io.BytesIO(xlsx_resp.content))
    summary = wb["Executive Summary"]
    ledger = wb["Reconciled Ledger"]
    exceptions = wb["Exceptions & Discrepancies"]
    assert summary["B9"].value == 4
    assert summary["B10"].value == 1
    assert ledger.max_row == 7  # header + 4 rows + blank + Total row
    assert exceptions.max_row == 4  # header + 1 row + blank + Total row

    assert xml_resp.status_code == 200
    root = ET.fromstring(xml_resp.text)
    vouchers = root.findall(".//VOUCHER")
    assert len(vouchers) == 4


async def test_exports_do_not_truncate_over_ten_thousand_rows(monkeypatch):
    """All 10,005 records must appear in CSV, XLSX, and Tally XML outputs."""
    total_rows = 10_005
    tx_date = datetime(2026, 3, 1, tzinfo=UTC)
    synthetic_logs = [
        SimpleNamespace(
            id=f"log-{i:05d}",
            batch_id="large-batch",
            match_status="MATCHED",
            match_tier="TIER_1",
            confidence_score=1.0,
            diagnostic_type="EXACT_MATCH",
            diagnostic_note=f"row-{i}",
            human_action="AUTO",
            delta_amount=Decimal("0.00"),
            bank_transaction=SimpleNamespace(
                date=tx_date,
                direction="CREDIT",
                description=f"Merchant payout {i}",
                utr=f"UTR{i:05d}",
                amount=Decimal("100.00"),
            ),
            rzp_settlement=SimpleNamespace(
                settlement_id=f"setl_{i:05d}",
                created_at=tx_date,
                amount=Decimal("100.00"),
                gross_amount=Decimal("102.36"),
                fees=Decimal("2.00"),
                tax=Decimal("0.36"),
            ),
        )
        for i in range(total_rows)
    ]

    class PaginatedStubRepo:
        async def get_active_logs(self, *, batch_id: str, page: int = 1, page_size: int = 100):
            assert batch_id == "large-batch"
            start = (page - 1) * page_size
            end = start + page_size
            return synthetic_logs[start:end], len(synthetic_logs)

    monkeypatch.setattr(reconciliation_api, "ReconciliationRepository", lambda db: PaginatedStubRepo())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        csv_resp = await client.get("/api/v1/reconciliation/large-batch/export")
        xlsx_resp = await client.get("/api/v1/reconciliation/large-batch/export-xlsx")
        xml_resp = await client.get("/api/v1/reconciliation/large-batch/export-tally-xml")

    assert csv_resp.status_code == 200
    csv_rows = list(csv.DictReader(io.StringIO(csv_resp.text, newline="")))
    assert len(csv_rows) == total_rows
    assert csv_rows[-1]["Bank UTR"] == "UTR10004"

    assert xlsx_resp.status_code == 200
    wb = load_workbook(io.BytesIO(xlsx_resp.content))
    assert wb["Executive Summary"]["B9"].value == total_rows
    assert wb["Reconciled Ledger"][f"B{total_rows + 1}"].value == "UTR10004"

    assert xml_resp.status_code == 200
    vouchers = ET.fromstring(xml_resp.text).findall(".//VOUCHER")
    assert len(vouchers) == total_rows


async def test_exports_handle_empty_batch_cleanly(db_session):
    """Empty batches return valid CSV header, XLSX workbook, and Tally XML envelope."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        csv_resp = await client.get("/api/v1/reconciliation/empty-batch/export")
        xlsx_resp = await client.get("/api/v1/reconciliation/empty-batch/export-xlsx")
        xml_resp = await client.get("/api/v1/reconciliation/empty-batch/export-tally-xml")

    assert csv_resp.status_code == 200
    csv_rows = list(csv.DictReader(io.StringIO(csv_resp.text, newline="")))
    assert csv_rows == []
    assert csv_resp.text.startswith("Date,Direction,Bank Description")

    assert xlsx_resp.status_code == 200
    wb = load_workbook(io.BytesIO(xlsx_resp.content))
    assert wb["Executive Summary"]["B9"].value == 0

    assert xml_resp.status_code == 200
    vouchers = ET.fromstring(xml_resp.text).findall(".//VOUCHER")
    assert vouchers == []
