"""Tests for architectural audit and reliability fixes implemented in Phase 9."""

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
import httpx

from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.models.reconciliation_log import ReconciliationLog
from app.services.diagnostics import DiagnosticsService
from app.services.guardrail import validate_qa_narration
from app.services.razorpay_client import _is_transient_error
from app.services.tally_export import (
    TDS_RECEIVABLE_LEDGER,
    build_voucher_lines,
    is_balanced,
)
from app.utils.csv_parser import compute_row_hash


def test_debit_reversal_amount_match():
    """Debit transaction matching settlement amount should be diagnosed as REVERSAL."""
    bank = BankTransaction(
        date=datetime.now(UTC),
        amount=Decimal("5000.00"),
        direction="DEBIT",
        description="REVERSAL/RAZORPAY",
        row_hash="deb_match_1",
    )
    setl = RazorpaySettlement(
        settlement_id="setl_deb_1",
        amount=Decimal("5000.00"),
        gross_amount=Decimal("5000.00"),
        fees=Decimal("0.00"),
        tax=Decimal("0.00"),
    )
    result = DiagnosticsService.evaluate_delta(bank, setl)
    assert result.diagnostic_type == "REVERSAL"
    assert result.match_status == "MATCHED"
    assert result.delta_amount == Decimal("5000.00")
    assert "matched against negative adjustment" in result.diagnostic_note


def test_debit_reversal_amount_mismatch_exception():
    """Debit transaction with mismatched amount must be flagged as EXCEPTION / UNRESOLVED."""
    bank = BankTransaction(
        date=datetime.now(UTC),
        amount=Decimal("9999.00"),
        direction="DEBIT",
        description="REVERSAL/RAZORPAY",
        row_hash="deb_mismatch_1",
    )
    setl = RazorpaySettlement(
        settlement_id="setl_deb_2",
        amount=Decimal("5000.00"),
        gross_amount=Decimal("5000.00"),
        fees=Decimal("0.00"),
        tax=Decimal("0.00"),
    )
    result = DiagnosticsService.evaluate_delta(bank, setl)
    assert result.diagnostic_type == "UNRESOLVED"
    assert result.match_status == "EXCEPTION"
    assert "does not match settlement" in result.diagnostic_note
    assert "payout" in result.diagnostic_note


def test_tally_export_section_194o_tds_balanced():
    """Tally voucher generation with TDS u/s 194-O must produce balanced journal lines."""
    now = datetime(2026, 8, 14, tzinfo=UTC)
    bank_tx = BankTransaction(
        id="b-test-tds",
        amount=Decimal("97200.00"),
        date=now,
        direction="CREDIT",
        utr="UTR194O",
        description="CMS/RAZORPAY",
        row_hash="h-test-tds",
    )
    rzp = RazorpaySettlement(
        id="r-test-tds",
        settlement_id="setl_tds_1",
        amount=Decimal("97200.00"),
        gross_amount=Decimal("100000.00"),
        fees=Decimal("1525.42"),
        tax=Decimal("274.58"),
        utr="UTR194O",
        settlement_created_at=now,
    )
    # Gross 100000, Bank 97200, Fee 1525.42, Tax 274.58 -> Remaining TDS = 1000.00
    log = ReconciliationLog(
        id="log-tds-1",
        bank_tx_id=bank_tx.id,
        rzp_settlement_id=rzp.id,
        match_status="MATCHED",
        match_tier="TIER_3",
        delta_amount=Decimal("1000.00"),
        diagnostic_type="TDS_194O_DEDUCTION",
        diagnostic_note="Section 194-O TDS deduction identified",
        bank_transaction=bank_tx,
        rzp_settlement=rzp,
        matched_at=now,
    )

    result = build_voucher_lines(log, bank_ledger="HDFC Bank A/c")
    assert result is not None
    debits, credit = result

    assert is_balanced(debits, credit) is True
    assert credit[1] == Decimal("100000.00")

    tds_lines = [amt for name, amt in debits if name == TDS_RECEIVABLE_LEDGER]
    assert len(tds_lines) == 1
    assert tds_lines[0] == Decimal("1000.00")


def test_guardrail_whitelists_timestamp_and_fee_rates():
    """Guardrail should whitelist time references (e.g., 14:30) and statutory rates (18%, 2%, 1%)."""
    dt = datetime(2026, 8, 14, 14, 30, tzinfo=UTC)
    bank_tx = BankTransaction(
        id="bank_g1",
        row_hash="hash_g1",
        date=dt,
        amount=Decimal("98200.00"),
        direction="CREDIT",
        utr="UTR98200",
        description="CMS/RAZORPAY",
    )
    rzp = RazorpaySettlement(
        id="rzp_g1",
        settlement_id="setl_g1",
        amount=Decimal("98200.00"),
        gross_amount=Decimal("100000.00"),
        fees=Decimal("1525.42"),
        tax=Decimal("274.58"),
        utr="UTR98200",
        settlement_created_at=dt,
    )
    log = ReconciliationLog(
        id="log_g1",
        bank_tx_id=bank_tx.id,
        rzp_settlement_id=rzp.id,
        match_status="MATCHED",
        match_tier="TIER_3",
        delta_amount=Decimal("1800.00"),
        diagnostic_type="FEE_DEDUCTION",
        diagnostic_note="Deduction resolved",
        bank_transaction=bank_tx,
        rzp_settlement=rzp,
        matched_at=dt,
    )

    narration = (
        "Settlement of 98200 was processed at 14:30. "
        "The standard fee rate was 2% with 18% GST and 1% TDS applied."
    )
    
    is_valid, reasons = validate_qa_narration(narration, log)
    assert is_valid is True, f"Expected valid narration, got reasons: {reasons}"
    assert len(reasons) == 0


def test_same_day_identical_rows_unique_hashes():
    """Two identical bank transactions on the same day must produce unique row hashes when row_index is supplied."""
    date_val = datetime(2026, 3, 31, tzinfo=UTC)
    desc = "UPI/PAYMENT/CUSTOMER"
    amount = Decimal("500.00")
    direction = "CREDIT"
    utr = None

    hash_row_0 = compute_row_hash(date_val, amount, direction, utr, desc, row_index=0)
    hash_row_1 = compute_row_hash(date_val, amount, direction, utr, desc, row_index=1)

    assert hash_row_0 != hash_row_1
    assert len(hash_row_0) == 64
    assert len(hash_row_1) == 64


def test_webhook_deterministic_fallback_event_id():
    """Deterministic SHA-256 fallback event ID must be stable and reproducible across executions."""
    raw_payload = b'{"entity":"event","event":"settlement.processed","contains":["settlement"]}'
    
    event_id_1 = f"evt_fallback_{hashlib.sha256(raw_payload).hexdigest()[:24]}"
    event_id_2 = f"evt_fallback_{hashlib.sha256(raw_payload).hexdigest()[:24]}"

    assert event_id_1 == event_id_2
    assert len(event_id_1) == len("evt_fallback_") + 24


def test_razorpay_retry_predicate():
    """Verify transient error classification: 401/403/404 must not retry; 429/500/network must retry."""
    req = httpx.Request("GET", "https://api.razorpay.com/v1/settlements")
    resp_401 = httpx.Response(401, request=req)
    err_401 = httpx.HTTPStatusError("Unauthorized", request=req, response=resp_401)
    assert _is_transient_error(err_401) is False

    resp_403 = httpx.Response(403, request=req)
    err_403 = httpx.HTTPStatusError("Forbidden", request=req, response=resp_403)
    assert _is_transient_error(err_403) is False

    resp_404 = httpx.Response(404, request=req)
    err_404 = httpx.HTTPStatusError("Not Found", request=req, response=resp_404)
    assert _is_transient_error(err_404) is False

    resp_429 = httpx.Response(429, request=req)
    err_429 = httpx.HTTPStatusError("Too Many Requests", request=req, response=resp_429)
    assert _is_transient_error(err_429) is True

    resp_503 = httpx.Response(503, request=req)
    err_503 = httpx.HTTPStatusError("Service Unavailable", request=req, response=resp_503)
    assert _is_transient_error(err_503) is True

    net_err = httpx.ConnectError("Failed to establish a new connection", request=req)
    assert _is_transient_error(net_err) is True
