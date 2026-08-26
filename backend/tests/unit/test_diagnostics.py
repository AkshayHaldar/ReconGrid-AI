"""Unit tests for Tier 3 deterministic discrepancy diagnostics."""

from datetime import datetime, timezone
from decimal import Decimal
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.services.diagnostics import DiagnosticsService


def test_diagnostics_exact_match():
    bank = BankTransaction(
        date=datetime.now(timezone.utc),
        amount=Decimal("98200.00"),
        direction="CREDIT",
        description="CMS/RAZORPAY",
        row_hash="h1",
    )
    setl = RazorpaySettlement(
        settlement_id="setl_1",
        amount=Decimal("98200.00"),
        gross_amount=Decimal("100000.00"),
        fees=Decimal("1525.42"),
        tax=Decimal("274.58"),
    )
    result = DiagnosticsService.evaluate_delta(bank, setl)
    assert result.diagnostic_type == "EXACT_MATCH"
    assert result.match_status == "MATCHED"
    assert result.delta_amount == Decimal("0.00")


def test_diagnostics_fee_gst_deduction():
    bank = BankTransaction(
        date=datetime.now(timezone.utc),
        amount=Decimal("49100.00"),
        direction="CREDIT",
        description="CMS/RAZORPAY",
        row_hash="h2",
    )
    setl = RazorpaySettlement(
        settlement_id="setl_2",
        amount=Decimal("49100.00"),
        gross_amount=Decimal("50000.00"),
        fees=Decimal("762.71"),
        tax=Decimal("137.29"),
    )
    # Bank shows 49,100 (net) against 50,000 gross with 762.71 fee + 137.29 GST = 900
    result = DiagnosticsService.evaluate_delta(bank, setl)
    assert result.diagnostic_type in {"FEE_DEDUCTION", "EXACT_MATCH"}
    assert result.match_status == "MATCHED"


def test_diagnostics_refund_adjustment():
    bank = BankTransaction(
        date=datetime.now(timezone.utc),
        amount=Decimal("68500.00"),
        direction="CREDIT",
        description="CMS/REFUND",
        row_hash="h3",
    )
    setl = RazorpaySettlement(
        settlement_id="setl_3",
        amount=Decimal("68500.00"),
        gross_amount=Decimal("75000.00"),
        fees=Decimal("1271.19"),
        tax=Decimal("228.81"),
        raw_payload={"refund_total": Decimal("5000.00")},
    )
    result = DiagnosticsService.evaluate_delta(bank, setl)
    assert result.match_status == "MATCHED"
    assert result.diagnostic_type in {"REFUND_ADJUSTED", "EXACT_MATCH"}


def test_diagnostics_debit_reversal():
    bank = BankTransaction(
        date=datetime.now(timezone.utc),
        amount=Decimal("15000.00"),
        direction="DEBIT",
        description="DR/REVERSAL",
        row_hash="h4",
    )
    setl = RazorpaySettlement(
        settlement_id="setl_4",
        amount=Decimal("15000.00"),
        gross_amount=Decimal("15000.00"),
    )
    result = DiagnosticsService.evaluate_delta(bank, setl)
    assert result.diagnostic_type == "REVERSAL"
    assert result.match_status == "MATCHED"


def test_diagnostics_fx_adjustment():
    bank = BankTransaction(
        date=datetime.now(timezone.utc),
        amount=Decimal("82150.00"),
        direction="CREDIT",
        description="CMS/FX",
        row_hash="h_fx",
    )
    setl = RazorpaySettlement(
        settlement_id="setl_fx",
        amount=Decimal("82150.00"),
        gross_amount=Decimal("85000.00"),
        fees=Decimal("1440.68"),
        tax=Decimal("259.32"),
        raw_payload={"fx_fee": Decimal("1150.00")},
    )
    result = DiagnosticsService.evaluate_delta(bank, setl)
    assert result.match_status == "MATCHED"
    assert result.diagnostic_type in {"FX_ADJUSTED", "EXACT_MATCH"}


def test_diagnostics_unresolved_delta():
    bank = BankTransaction(
        date=datetime.now(timezone.utc),
        amount=Decimal("10000.00"),
        direction="CREDIT",
        description="CMS/UNMATCHED",
        row_hash="h_unres",
    )
    setl = RazorpaySettlement(
        settlement_id="setl_unres",
        amount=Decimal("50000.00"),
        gross_amount=Decimal("50000.00"),
        fees=Decimal("0.00"),
        tax=Decimal("0.00"),
    )
    result = DiagnosticsService.evaluate_delta(bank, setl)
    assert result.match_status == "EXCEPTION"
    assert result.diagnostic_type == "UNRESOLVED"
    assert result.delta_amount == Decimal("40000.00")


def test_diagnostics_mdr_2percent_estimation():
    bank = BankTransaction(
        date=datetime.now(timezone.utc),
        amount=Decimal("97640.00"),  # 100000 - 2000 (2%) - 360 (18% GST on 2000) = 97640
        direction="CREDIT",
        description="CMS/RAZORPAY",
        row_hash="h_mdr",
    )
    setl = RazorpaySettlement(
        settlement_id="setl_mdr",
        amount=Decimal("100000.00"),
        gross_amount=Decimal("100000.00"),
        fees=Decimal("0.00"),
        tax=Decimal("0.00"),
    )
    result = DiagnosticsService.evaluate_delta(bank, setl)
    assert result.match_status == "MATCHED"
    assert result.diagnostic_type == "FEE_DEDUCTION"
    assert "standard 2% Gateway Fee" in result.diagnostic_note


def test_diagnostics_tds_194o_deduction():
    bank = BankTransaction(
        date=datetime.now(timezone.utc),
        amount=Decimal("97200.00"),  # 100000 - 1000 TDS 1% - 1525.42 fee - 274.58 tax = 97200
        direction="CREDIT",
        description="CMS/RAZORPAY/194O",
        row_hash="h_tds",
    )
    setl = RazorpaySettlement(
        settlement_id="setl_tds",
        amount=Decimal("97200.00"),
        gross_amount=Decimal("100000.00"),
        fees=Decimal("1525.42"),
        tax=Decimal("274.58"),
    )
    result = DiagnosticsService.evaluate_delta(bank, setl)
    assert result.match_status == "MATCHED"
    assert result.diagnostic_type == "TDS_194O_DEDUCTION"
    assert "1% TDS u/s 194-O" in result.diagnostic_note
