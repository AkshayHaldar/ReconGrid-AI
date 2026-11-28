"""Comprehensive unit tests for multi-bank streaming CSV parser covering all supported dialects and edge cases."""

from datetime import UTC, datetime
from decimal import Decimal

from app.utils.csv_parser import (
    BankCsvParser,
    compute_row_hash,
    extract_utr_from_text,
    parse_flexible_date,
)


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
    dt = datetime(2026, 8, 24, tzinfo=UTC)
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


def test_parse_utf8_bom_prefixed_csv():
    # Prepend UTF-8 BOM character to header
    bom_csv_lines = [
        "﻿Date,Chq/Ref No.,Narration,Deposit Amt.,Withdrawal Amt.",
        "24/08/2026,CMS002938491801,CMS/002938491801/HDFC,98200.00,0.00",
    ]
    rows = list(BankCsvParser.parse_csv_stream(iter(bom_csv_lines)))
    assert len(rows) == 1
    assert rows[0]["amount"] == Decimal("98200.00")
    assert rows[0]["utr"] == "CMS002938491801"
    assert rows[0]["direction"] == "CREDIT"


def test_parse_indian_lakh_crore_comma_amounts():
    csv_lines = [
        "Date,Chq/Ref No.,Narration,Deposit Amt.,Withdrawal Amt.",
        '24/08/2026,CMS002938491820,CMS/002938491820/HDFC,"1,23,456.78",0.00',
        '25/08/2026,CMS002938491821,CMS/002938491821/HDFC,"12,34,56,789.50",0.00',
    ]
    rows = list(BankCsvParser.parse_csv_stream(iter(csv_lines)))
    assert len(rows) == 2
    assert rows[0]["amount"] == Decimal("123456.78")
    assert rows[1]["amount"] == Decimal("123456789.50")


def test_parse_custom_column_mappings():
    # Non-standard headers e.g. corporate bank portal (Axis / IndusInd / Federal / Yes Bank)
    csv_lines = [
        "Value Date,Particulars,Instrument Id,Deposit,Withdrawal,Balance",
        "24-08-2026,SETTLEMENT RAZORPAY BANGALORE,CMS002938491850,85000.00,0.00,185000.00",
        "25-08-2026,SMS ALERT CHARGES,INST12345678,0.00,59.00,184941.00",
    ]
    custom_mappings = {
        "date": "Value Date",
        "narration": "Particulars",
        "ref": "Instrument Id",
        "amount": "Deposit",
    }
    rows = list(BankCsvParser.parse_csv_stream(iter(csv_lines), custom_mappings=custom_mappings))
    assert len(rows) == 1
    assert rows[0]["amount"] == Decimal("85000.00")
    assert rows[0]["direction"] == "CREDIT"
    assert rows[0]["utr"] == "CMS002938491850"
    assert rows[0]["description"] == "SETTLEMENT RAZORPAY BANGALORE"


def test_parse_custom_column_mappings_with_preamble():
    csv_lines = [
        "Federal Bank Limited",
        "Customer Statement for Account 123456789",
        "Period: 01-Aug-2026 to 31-Aug-2026",
        "",
        "Txn Date,Narrative,Doc Number,Paid In,Paid Out,Running Balance",
        "24/08/2026,RAZORPAY SETTLEMENT CMS8899001122,CMS8899001122,64200.00,0.00,264200.00",
    ]
    custom_mappings = {
        "date": "Txn Date",
        "narration": "Narrative",
        "ref": "Doc Number",
        "amount": "Paid In",
    }
    rows = list(BankCsvParser.parse_csv_stream(iter(csv_lines), custom_mappings=custom_mappings))
    assert len(rows) == 1
    assert rows[0]["amount"] == Decimal("64200.00")
    assert rows[0]["direction"] == "CREDIT"
    assert rows[0]["utr"] == "CMS8899001122"
    assert rows[0]["description"] == "RAZORPAY SETTLEMENT CMS8899001122"


def test_parse_duplicate_headers_with_index_mapping():
    """Verify duplicate headers disambiguated by column indices correctly map credit and debit columns."""
    csv_lines = [
        "Date,Narration,Amount,Amount,Balance",
        "24/08/2026,Credit Txn,5000.00,0.00,15000.00",
        "25/08/2026,Debit Txn,0.00,2000.00,13000.00",
    ]
    # Column 2 is deposit (Amount), Column 3 is withdrawal (Amount)
    custom_mappings = {
        "date": 0,
        "narration": 1,
        "amount": 2,
        "withdrawal": 3,
    }
    rows = list(BankCsvParser.parse_csv_stream(iter(csv_lines), custom_mappings=custom_mappings))
    assert len(rows) == 2

    # Row 1 is a credit of 5000.00
    assert rows[0]["amount"] == Decimal("5000.00")
    assert rows[0]["direction"] == "CREDIT"
    assert rows[0]["description"] == "Credit Txn"

    # Row 2 is a debit of 2000.00
    assert rows[1]["amount"] == Decimal("2000.00")
    assert rows[1]["direction"] == "DEBIT"
    assert rows[1]["description"] == "Debit Txn"


def test_parse_separate_credit_and_debit_columns():
    """Verify statements with separate credit (Paid In) and debit (Paid Out) columns capture both directions."""
    csv_lines = [
        "Txn Date,Particulars,Instrument ID,Paid In,Paid Out,Balance",
        "24/08/2026,Customer Inward CMS002938491850,CMS002938491850,85000.00,0.00,185000.00",
        "25/08/2026,Vendor Outward CMS002938491851,CMS002938491851,0.00,34000.00,151000.00",
    ]
    custom_mappings = {
        "date": "Txn Date",
        "narration": "Particulars",
        "ref": "Instrument ID",
        "amount": "Paid In",
        "withdrawal": "Paid Out",
    }
    rows = list(BankCsvParser.parse_csv_stream(iter(csv_lines), custom_mappings=custom_mappings))
    assert len(rows) == 2

    assert rows[0]["amount"] == Decimal("85000.00")
    assert rows[0]["direction"] == "CREDIT"
    assert rows[0]["utr"] == "CMS002938491850"

    assert rows[1]["amount"] == Decimal("34000.00")
    assert rows[1]["direction"] == "DEBIT"
    assert rows[1]["utr"] == "CMS002938491851"


def test_parse_multiline_quoted_narration():
    """Verify multiline quoted fields with embedded newlines are preserved in description without breaking row count."""
    csv_lines = [
        "Date,Narration,Deposit Amt.,Withdrawal Amt.\n",
        '24/08/2026,"Settlement for Order #99102\nClient: ACME Corp Bangalore",42000.00,0.00\n',
        "25/08/2026,Direct Debit Bank Charge,0.00,150.00\n",
    ]
    rows = list(BankCsvParser.parse_csv_stream(iter(csv_lines)))
    assert len(rows) == 2
    assert "Settlement for Order #99102" in rows[0]["description"]
    assert "Client: ACME Corp Bangalore" in rows[0]["description"]
    assert rows[0]["amount"] == Decimal("42000.00")
    assert rows[1]["amount"] == Decimal("150.00")


def test_parse_generic_signed_amount_with_explicit_direction():
    """Verify generic amount with explicit CR/DR direction column."""
    csv_lines = [
        "Value Date,Narrative,Reference,Amount,CR_DR_Flag",
        "24/08/2026,Incoming NEFT CMS0011223344,CMS0011223344,12000.00,CR",
        "25/08/2026,Outgoing Payment CMS0011223355,CMS0011223355,4500.00,DR",
    ]
    custom_mappings = {
        "date": "Value Date",
        "narration": "Narrative",
        "ref": "Reference",
        "amount": "Amount",
        "direction": "CR_DR_Flag",
    }
    rows = list(BankCsvParser.parse_csv_stream(iter(csv_lines), custom_mappings=custom_mappings))
    assert len(rows) == 2
    assert rows[0]["amount"] == Decimal("12000.00")
    assert rows[0]["direction"] == "CREDIT"
    assert rows[1]["amount"] == Decimal("4500.00")
    assert rows[1]["direction"] == "DEBIT"


def test_parse_preamble_up_to_30_lines():
    """Verify preamble detection searches up to line 30 for the header row."""
    lines = [f"Metadata Header Line {i}" for i in range(1, 30)]  # 29 metadata lines
    lines.append("Posting Date,Description,Ref Number,Credit,Debit")  # Line 30 (header)
    lines.append("24/08/2026,Razorpay Batch CMS1122334455,CMS1122334455,75000.00,0.00")
    custom_mappings = {
        "date": "Posting Date",
        "narration": "Description",
        "ref": "Ref Number",
        "amount": "Credit",
        "withdrawal": "Debit",
    }
    rows = list(BankCsvParser.parse_csv_stream(iter(lines), custom_mappings=custom_mappings))
    assert len(rows) == 1
    assert rows[0]["amount"] == Decimal("75000.00")
    assert rows[0]["direction"] == "CREDIT"
    assert rows[0]["utr"] == "CMS1122334455"
