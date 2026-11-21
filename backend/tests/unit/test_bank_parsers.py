"""Comprehensive unit tests for Axis Bank and Kotak Mahindra Bank statement parsers.

Validates:
- 100% row conservation (no dropped records)
- Strict Zero-Float Policy (all amounts are Decimal)
- Deep preamble resilience (10-50 metadata lines)
- Dual-column and single-amount + DR/CR direction resolution
- Embedded 12-char UTR extraction when explicit reference is placeholder/empty
- Full regression safety across HDFC, ICICI, SBI, and Generic dialects
"""

import io
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ingestion import IngestionService
from app.utils.csv_parser import (
    BankCsvParser,
    is_placeholder_ref,
    is_zero_or_placeholder_amount,
    parse_flexible_date,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_axis_sample_fixture_parsing():
    """Verify Axis Bank sample fixture parses with 100% row conservation, exact directions, and zero floats."""
    fixture_path = FIXTURES_DIR / "axis_sample.csv"
    assert fixture_path.exists(), f"Missing fixture: {fixture_path}"

    with open(fixture_path, encoding="utf-8") as f:
        lines = f.readlines()

    rows = list(BankCsvParser.parse_csv_stream(iter(lines)))
    assert len(rows) == 6, f"Expected 6 rows, got {len(rows)}"

    # Zero-Float policy assertion: all amounts must be Decimal, zero float instances
    for r in rows:
        assert isinstance(r["amount"], Decimal)
        assert not isinstance(r["amount"], float)

    # Row 1: Credit 98,200.00, UTR from narration (ref was 000000)
    assert rows[0]["date"].strftime("%Y-%m-%d") == "2026-08-24"
    assert rows[0]["amount"] == Decimal("98200.00")
    assert rows[0]["direction"] == "CREDIT"
    assert rows[0]["utr"] == "202611210001"

    # Row 2: Debit 15,000.00, explicit ref UTIB002938491811
    assert rows[1]["date"].strftime("%Y-%m-%d") == "2026-08-25"
    assert rows[1]["amount"] == Decimal("15000.00")
    assert rows[1]["direction"] == "DEBIT"
    assert rows[1]["utr"] == "UTIB002938491811"

    # Row 3: Credit 4,500.50, UTR from narration (ref was -)
    assert rows[2]["date"].strftime("%Y-%m-%d") == "2026-08-26"
    assert rows[2]["amount"] == Decimal("4500.50")
    assert rows[2]["direction"] == "CREDIT"
    assert rows[2]["utr"] == "632512345678"

    # Row 4: Debit 32,000.00, explicit cheque ref
    assert rows[3]["date"].strftime("%Y-%m-%d") == "2026-08-27"
    assert rows[3]["amount"] == Decimal("32000.00")
    assert rows[3]["direction"] == "DEBIT"
    assert rows[3]["utr"] == "CHQ100294"

    # Row 5: Credit 1,25,000.00 (Indian lakh comma formatted), UTR from narration (ref was 000000)
    assert rows[4]["date"].strftime("%Y-%m-%d") == "2026-08-28"
    assert rows[4]["amount"] == Decimal("125000.00")
    assert rows[4]["direction"] == "CREDIT"
    assert rows[4]["utr"] == "AXISCN0012345678"

    # Row 6: Debit 590.00, ref was NA (no UTR in description)
    assert rows[5]["date"].strftime("%Y-%m-%d") == "2026-08-29"
    assert rows[5]["amount"] == Decimal("590.00")
    assert rows[5]["direction"] == "DEBIT"
    assert rows[5]["utr"] is None


def test_kotak_sample_fixture_parsing():
    """Verify Kotak Mahindra sample fixture parses with 100% row conservation, dual columns, and zero floats."""
    fixture_path = FIXTURES_DIR / "kotak_sample.csv"
    assert fixture_path.exists(), f"Missing fixture: {fixture_path}"

    with open(fixture_path, encoding="utf-8") as f:
        lines = f.readlines()

    rows = list(BankCsvParser.parse_csv_stream(iter(lines)))
    assert len(rows) == 6, f"Expected 6 rows, got {len(rows)}"

    for r in rows:
        assert isinstance(r["amount"], Decimal)
        assert not isinstance(r["amount"], float)

    # Row 1: Credit 75,000.00, UTR from narration (ref was -)
    assert rows[0]["date"].strftime("%Y-%m-%d") == "2026-08-24"
    assert rows[0]["amount"] == Decimal("75000.00")
    assert rows[0]["direction"] == "CREDIT"
    assert rows[0]["utr"] == "202611210002"

    # Row 2: Debit 40,000.00, explicit ref KKBKH26325000123
    assert rows[1]["date"].strftime("%Y-%m-%d") == "2026-08-25"
    assert rows[1]["amount"] == Decimal("40000.00")
    assert rows[1]["direction"] == "DEBIT"
    assert rows[1]["utr"] == "KKBKH26325000123"

    # Row 3: Credit 1,20,000.00, UTR from narration (ref was 000000)
    assert rows[2]["date"].strftime("%Y-%m-%d") == "2026-08-26"
    assert rows[2]["amount"] == Decimal("120000.00")
    assert rows[2]["direction"] == "CREDIT"
    assert rows[2]["utr"] == "002938491899"

    # Row 4: Debit 1,500.00, ref was NA (no UTR in description)
    assert rows[3]["date"].strftime("%Y-%m-%d") == "2026-08-27"
    assert rows[3]["amount"] == Decimal("1500.00")
    assert rows[3]["direction"] == "DEBIT"
    assert rows[3]["utr"] is None

    # Row 5: Credit 18,450.75, UTR from narration (ref was -)
    assert rows[4]["date"].strftime("%Y-%m-%d") == "2026-08-28"
    assert rows[4]["amount"] == Decimal("18450.75")
    assert rows[4]["direction"] == "CREDIT"
    assert rows[4]["utr"] == "632599887766"

    # Row 6: Debit 12,850.00, explicit cheque ref 500122
    assert rows[5]["date"].strftime("%Y-%m-%d") == "2026-08-29"
    assert rows[5]["amount"] == Decimal("12850.00")
    assert rows[5]["direction"] == "DEBIT"
    assert rows[5]["utr"] == "500122"


def test_axis_direction_collision_guard():
    """Verify detect_headers prevents DR/CR from erroneously binding to withdrawal or deposit."""
    fieldnames = ["Tran Date", "CHQ/REF NO", "PARTICULARS", "DR/CR", "TRAN AMT", "BAL"]
    mapping = BankCsvParser.detect_headers(fieldnames)

    assert mapping.get("date") == "Tran Date"
    assert mapping.get("narration") == "PARTICULARS"
    assert mapping.get("ref") == "CHQ/REF NO"
    assert mapping.get("amount") == "TRAN AMT"
    assert mapping.get("direction") == "DR/CR"

    # Guard check: DR/CR must NOT be mapped to withdrawal or deposit
    assert mapping.get("withdrawal") != "DR/CR"
    assert mapping.get("deposit") != "DR/CR"
    assert "withdrawal" not in mapping
    assert "deposit" not in mapping


def test_axis_separate_credit_debit_columns():
    """Verify Axis statement with distinct CR and DR amount columns parses properly."""
    lines = [
        "Tran Date,CHQNO,PARTICULARS,CR,DR",
        "24/08/2026,UTIB002938491811,AXIS/RZP/CMS002938491811,32000.00,0.00",
        "25/08/2026,UTIB002938491812,AXIS/VENDOR/PAYMENT,0.00,12500.00",
    ]
    rows = list(BankCsvParser.parse_csv_stream(iter(lines)))
    assert len(rows) == 2
    assert rows[0]["amount"] == Decimal("32000.00")
    assert rows[0]["direction"] == "CREDIT"
    assert rows[0]["utr"] == "UTIB002938491811"

    assert rows[1]["amount"] == Decimal("12500.00")
    assert rows[1]["direction"] == "DEBIT"
    assert rows[1]["utr"] == "UTIB002938491812"


def test_kotak_placeholder_and_utr_extraction():
    """Verify various placeholder references fall back to narration UTR extraction."""
    assert is_placeholder_ref("000000") is True
    assert is_placeholder_ref("0") is True
    assert is_placeholder_ref("-") is True
    assert is_placeholder_ref("--") is True
    assert is_placeholder_ref("NA") is True
    assert is_placeholder_ref("N/A") is True
    assert is_placeholder_ref("NIL") is True
    assert is_placeholder_ref("NONE") is True
    assert is_placeholder_ref("") is True
    assert is_placeholder_ref(None) is True
    assert is_placeholder_ref("000000000000") is True

    # Real references are NOT placeholders
    assert is_placeholder_ref("CMS002938491801") is False
    assert is_placeholder_ref("KKBKH26325000123") is False
    assert is_placeholder_ref("UTIB002938491811") is False
    assert is_placeholder_ref("500122") is False


def test_is_zero_or_placeholder_amount():
    """Verify zero and placeholder amount detector correctly identifies non-amounts."""
    assert is_zero_or_placeholder_amount("-") is True
    assert is_zero_or_placeholder_amount("--") is True
    assert is_zero_or_placeholder_amount("0.00") is True
    assert is_zero_or_placeholder_amount("0") is True
    assert is_zero_or_placeholder_amount("NA") is True
    assert is_zero_or_placeholder_amount("") is True
    assert is_zero_or_placeholder_amount(None) is True

    assert is_zero_or_placeholder_amount("100.00") is False
    assert is_zero_or_placeholder_amount("1,23,456.78") is False
    assert is_zero_or_placeholder_amount("0.01") is False


def test_preamble_resilience_up_to_50_lines():
    """Verify statement parser survives deep preambles with 45 metadata lines."""
    lines = [f"Kotak Bank Metadata Preamble Row {i},Customer Info,Detail" for i in range(1, 46)]
    lines.append("Transaction Date,Description,Ref No.,Debit (Dr),Credit (Cr)")
    lines.append("24/08/2026,UPI/202611210005/MERCHANT SETTLEMENT,-,-,88000.00")

    rows = list(BankCsvParser.parse_csv_stream(iter(lines)))
    assert len(rows) == 1
    assert rows[0]["amount"] == Decimal("88000.00")
    assert rows[0]["direction"] == "CREDIT"
    assert rows[0]["utr"] == "202611210005"


def test_flexible_date_parsing_formats():
    """Verify both DD-MM-YYYY and DD/MM/YYYY dates parse accurately without offset or shift."""
    d1 = parse_flexible_date("24-08-2026")
    assert d1.strftime("%Y-%m-%d") == "2026-08-24"

    d2 = parse_flexible_date("24/08/2026")
    assert d2.strftime("%Y-%m-%d") == "2026-08-24"

    d3 = parse_flexible_date("24/Aug/2026")
    assert d3.strftime("%Y-%m-%d") == "2026-08-24"

    d4 = parse_flexible_date("24-Aug-2026 15:30:00")
    assert d4.strftime("%Y-%m-%d") == "2026-08-24"


def test_bank_parser_regression_hdfc_icici_sbi():
    """Regression test ensuring HDFC, ICICI, and SBI continue to parse seamlessly."""
    # HDFC
    hdfc_lines = [
        "Date,Chq/Ref No.,Narration,Deposit Amt.,Withdrawal Amt.",
        "24/08/2026,CMS002938491801,CMS/002938491801/HDFC,98200.00,0.00",
    ]
    hdfc_rows = list(BankCsvParser.parse_csv_stream(iter(hdfc_lines)))
    assert len(hdfc_rows) == 1
    assert hdfc_rows[0]["amount"] == Decimal("98200.00")
    assert hdfc_rows[0]["direction"] == "CREDIT"
    assert hdfc_rows[0]["utr"] == "CMS002938491801"

    # ICICI
    icici_lines = [
        "Transaction Date,Transaction Reference Number,Transaction Remarks,Deposit Amount (INR ),Withdrawal Amount (INR )",
        "24/08/2026,CMS002938491805,CMS/002938491805/RAZORPAY,49100.00,0.00",
    ]
    icici_rows = list(BankCsvParser.parse_csv_stream(iter(icici_lines)))
    assert len(icici_rows) == 1
    assert icici_rows[0]["amount"] == Decimal("49100.00")
    assert icici_rows[0]["utr"] == "CMS002938491805"

    # SBI
    sbi_lines = [
        "Txn Date,Ref No./Cheque No.,Description,Credit,Debit",
        "24/08/2026,SBIN002938491809,SBI/SETTLEMENT/RAZORPAY,75000.00,0.00",
    ]
    sbi_rows = list(BankCsvParser.parse_csv_stream(iter(sbi_lines)))
    assert len(sbi_rows) == 1
    assert sbi_rows[0]["amount"] == Decimal("75000.00")
    assert sbi_rows[0]["direction"] == "CREDIT"


@pytest.mark.asyncio
async def test_ingestion_service_axis_and_kotak(db_session: AsyncSession):
    """End-to-end ingestion service verification using Axis and Kotak statement fixtures."""
    service = IngestionService(db_session)

    # Ingest Axis sample
    axis_fixture = FIXTURES_DIR / "axis_sample.csv"
    with open(axis_fixture, "rb") as f:
        axis_bytes = f.read()

    axis_file = UploadFile(
        filename="axis_sample.csv",
        file=io.BytesIO(axis_bytes),
        headers={"content-type": "text/csv"},
    )
    axis_resp = await service.ingest_csv(axis_file, batch_id="batch_axis_test")
    assert axis_resp.total_rows_parsed == 6
    assert axis_resp.inserted_count == 6
    assert axis_resp.duplicate_count == 0

    # Ingest Kotak sample
    kotak_fixture = FIXTURES_DIR / "kotak_sample.csv"
    with open(kotak_fixture, "rb") as f:
        kotak_bytes = f.read()

    kotak_file = UploadFile(
        filename="kotak_sample.csv",
        file=io.BytesIO(kotak_bytes),
        headers={"content-type": "text/csv"},
    )
    kotak_resp = await service.ingest_csv(kotak_file, batch_id="batch_kotak_test")
    assert kotak_resp.total_rows_parsed == 6
    assert kotak_resp.inserted_count == 6
    assert kotak_resp.duplicate_count == 0
