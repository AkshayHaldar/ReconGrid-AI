"""Unit tests for multi-bank streaming CSV parser."""

from decimal import Decimal
from app.utils.csv_parser import BankCsvParser, extract_utr_from_text


def test_extract_utr_from_text():
    assert extract_utr_from_text("CMS/002938491801/HDFC/RAZORPAY") == "002938491801"
    assert extract_utr_from_text("NEFT-CMS002938491803-SETTLEMENT") == "CMS002938491803"
    assert extract_utr_from_text("RTGS/CMS002938491804/PAYOUT") == "CMS002938491804"
    assert extract_utr_from_text("SHORT") is None


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
