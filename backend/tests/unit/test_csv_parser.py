"""Comprehensive unit tests for multi-bank streaming CSV parser covering all supported dialects and edge cases."""

from decimal import Decimal
from datetime import datetime, timezone
from app.utils.csv_parser import BankCsvParser, extract_utr_from_text, parse_flexible_date, compute_row_hash


def test_extract_utr_from_text():
    assert extract_utr_from_text("CMS/002938491801/HDFC/RAZORPAY") == "002938491801"
    assert extract_utr_from_text("NEFT-CMS002938491803-SETTLEMENT") == "CMS002938491803"
    assert extract_utr_from_text("RTGS/CMS002938491804/PAYOUT") == "CMS002938491804"
    assert extract_utr_from_text("UPI/123456789012/PAYMENT") == "123456789012"
    assert extract_utr_from_text("SHORT") is None
    assert extract_utr_from_text(None) is None
    assert extract_utr_from_text("") is None


def test_parse_flexible_dates():
    assert parse_flexible_date("2026-08-24").strftime("%Y-%m-%d") == "2026-08-24"
    assert parse_flexible_date("24/08/2026").strftime("%Y-%m-%d") == "2026-08-24"
    assert parse_flexible_date("24-08-2026").strftime("%Y-%m-%d") == "2026-08-24"
    assert parse_flexible_date("24/08/26").strftime("%Y-%m-%d") == "2026-08-24"
    assert parse_flexible_date("24-08-26").strftime("%Y-%m-%d") == "2026-08-24"
    assert parse_flexible_date("2026/08/24").strftime("%Y-%m-%d") == "2026-08-24"
    assert parse_flexible_date("24 Aug 2026").strftime("%Y-%m-%d") == "2026-08-24"
    assert parse_flexible_date("24-Aug-2026").strftime("%Y-%m-%d") == "2026-08-24"
    assert parse_flexible_date("2026-08-24 14:30:00").strftime("%Y-%m-%d") == "2026-08-24"

    # Raises ValueError on completely invalid string
    import pytest
    with pytest.raises(ValueError, match="Unable to parse date string"):
        parse_flexible_date("INVALID_DATE_STRING")


def test_compute_row_hash_deterministic():
    dt = datetime(2026, 8, 24, tzinfo=timezone.utc)
    h1 = compute_row_hash(dt, Decimal("98200.00"), "CREDIT", "CMS002938491801", "CMS/002938491801/HDFC")
    h2 = compute_row_hash(dt, Decimal("98200.00"), "CREDIT", "CMS002938491801", "CMS/002938491801/HDFC")
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex length


def test_parse_hdfc_format():
    csv_lines = [
        "Date,Chq/Ref No.,Narration,Deposit Amt.,Withdrawal Amt.",
        "24/08/2026,CMS002938491801,CMS/002938491801/HDFC,98200.00,0.00",
        "25/08/2026,CMS002938491808,DR/CMS002938491808/REVERSAL,0.00,15000.00",
    ]
    rows = list(BankCsvParser.parse_csv_stream(iter(csv_lines)))
    assert len(rows) == 2

    r1 = rows[0]
    assert r1["amount"] == Decimal("98200.00")
    assert r1["direction"] == "CREDIT"
    assert r1["utr"] == "CMS002938491801"

    r2 = rows[1]
    assert r2["amount"] == Decimal("15000.00")
    assert r2["direction"] == "DEBIT"


def test_parse_icici_format():
    csv_lines = [
        "Transaction Date,Transaction Reference Number,Transaction Remarks,Deposit Amount (INR ),Withdrawal Amount (INR )",
        "24/08/2026,CMS002938491805,CMS/002938491805/RAZORPAY,49100.00,0.00",
    ]
    rows = list(BankCsvParser.parse_csv_stream(iter(csv_lines)))
    assert len(rows) == 1
    assert rows[0]["amount"] == Decimal("49100.00")
    assert rows[0]["utr"] == "CMS002938491805"


def test_parse_sbi_format():
    csv_lines = [
        "Txn Date,Ref No./Cheque No.,Description,Credit,Debit",
        "24/08/2026,SBIN002938491809,SBI/SETTLEMENT/RAZORPAY,75000.00,0.00",
        "25/08/2026,SBIN002938491810,SBI/CHARGEBACK/DEBIT,0.00,2500.00",
    ]
    rows = list(BankCsvParser.parse_csv_stream(iter(csv_lines)))
    assert len(rows) == 2
    assert rows[0]["amount"] == Decimal("75000.00")
    assert rows[0]["direction"] == "CREDIT"
    assert rows[0]["utr"] == "SBIN002938491809"
    assert rows[1]["amount"] == Decimal("2500.00")
    assert rows[1]["direction"] == "DEBIT"


def test_parse_axis_format():
    csv_lines = [
        "Tran Date,CHQNO,PARTICULARS,CR,DR",
        "24/08/2026,UTIB002938491811,AXIS/RZP/CMS002938491811,32000.00,0.00",
    ]
    rows = list(BankCsvParser.parse_csv_stream(iter(csv_lines)))
    assert len(rows) == 1
    assert rows[0]["amount"] == Decimal("32000.00")
    assert rows[0]["direction"] == "CREDIT"
    assert rows[0]["utr"] == "UTIB002938491811"


def test_parse_generic_format_with_amount_and_direction():
    csv_lines = [
        "date,utr,description,amount,direction",
        "2026-08-24,GEN00123456789,Online Payout,54000.00,CREDIT",
        "2026-08-25,GEN00123456790,Refund Clawback,-1200.00,DEBIT",
    ]
    rows = list(BankCsvParser.parse_csv_stream(iter(csv_lines)))
    assert len(rows) == 2
    assert rows[0]["amount"] == Decimal("54000.00")
    assert rows[0]["direction"] == "CREDIT"
    assert rows[1]["amount"] == Decimal("1200.00")
    assert rows[1]["direction"] == "DEBIT"


def test_parse_empty_or_corrupted_csv():
    # Empty stream
    assert list(BankCsvParser.parse_csv_stream(iter([]))) == []

    # Whitespace and blank lines only
    blank_lines = ["Date,Ref,Narration,Deposit Amt.,Withdrawal Amt.", "", "   ", ",,,,"]
    assert list(BankCsvParser.parse_csv_stream(iter(blank_lines))) == []
