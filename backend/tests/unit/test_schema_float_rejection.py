"""Unit tests ensuring all Decimal monetary fields in Pydantic schemas explicitly reject raw floats."""

from datetime import datetime, timezone
from decimal import Decimal
import pytest
from pydantic import ValidationError

from app.schemas.bank import BankTransactionBase, BankTransactionCreate, BankTransactionResponse
from app.schemas.razorpay import RazorpaySettlementBase, RazorpaySettlementCreate, RazorpaySettlementResponse
from app.schemas.reconciliation import ReconciliationRecordItem, ReconciliationStatusResponse


def test_reconciliation_record_item_rejects_float_bank_amount():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError) as exc_info:
        ReconciliationRecordItem(
            id="rec_1",
            batch_id="batch_1",
            bank_tx_id="tx_1",
            date=now,
            bank_description="Razorpay payout",
            bank_amount=49999.99,  # float rejected!
            match_status="MATCHED",
            match_tier="TIER_0",
            diagnostic_type="EXACT_MATCH",
            diagnostic_note="Exact match",
            matched_at=now,
        )
    assert "Float values are strictly forbidden" in str(exc_info.value)


def test_reconciliation_record_item_rejects_float_optional_fields():
    now = datetime.now(timezone.utc)
    base_kwargs = dict(
        id="rec_1",
        batch_id="batch_1",
        bank_tx_id="tx_1",
        date=now,
        bank_description="Razorpay payout",
        bank_amount=Decimal("49999.99"),
        match_status="MATCHED",
        match_tier="TIER_0",
        diagnostic_type="EXACT_MATCH",
        diagnostic_note="Exact match",
        matched_at=now,
    )

    # Test rzp_amount float rejection
    with pytest.raises(ValidationError):
        ReconciliationRecordItem(**base_kwargs, rzp_amount=49999.99)

    # Test rzp_gross_amount float rejection
    with pytest.raises(ValidationError):
        ReconciliationRecordItem(**base_kwargs, rzp_gross_amount=50000.0)

    # Test rzp_fees float rejection
    with pytest.raises(ValidationError):
        ReconciliationRecordItem(**base_kwargs, rzp_fees=762.71)

    # Test rzp_tax float rejection
    with pytest.raises(ValidationError):
        ReconciliationRecordItem(**base_kwargs, rzp_tax=137.29)

    # Test delta_amount float rejection
    with pytest.raises(ValidationError):
        ReconciliationRecordItem(**base_kwargs, delta_amount=900.0)


def test_reconciliation_record_item_accepts_valid_types():
    now = datetime.now(timezone.utc)
    # Decimal
    item1 = ReconciliationRecordItem(
        id="rec_1",
        batch_id="batch_1",
        bank_tx_id="tx_1",
        date=now,
        bank_description="Razorpay payout",
        bank_amount=Decimal("49100.00"),
        rzp_amount=Decimal("49100.00"),
        rzp_gross_amount=Decimal("50000.00"),
        rzp_fees=Decimal("762.71"),
        rzp_tax=Decimal("137.29"),
        delta_amount=Decimal("900.00"),
        match_status="MATCHED",
        match_tier="TIER_3",
        diagnostic_type="FEE_DEDUCTION",
        diagnostic_note="Fee deduction",
        matched_at=now,
    )
    assert item1.bank_amount == Decimal("49100.00")

    # str
    item2 = ReconciliationRecordItem(
        id="rec_2",
        batch_id="batch_1",
        bank_tx_id="tx_2",
        date=now,
        bank_description="Razorpay payout",
        bank_amount="49100.00",
        rzp_amount="49100.00",
        delta_amount="0.00",
        match_status="MATCHED",
        match_tier="TIER_0",
        diagnostic_type="EXACT_MATCH",
        diagnostic_note="Exact match",
        matched_at=now,
    )
    assert item2.bank_amount == Decimal("49100.00")

    # int
    item3 = ReconciliationRecordItem(
        id="rec_3",
        batch_id="batch_1",
        bank_tx_id="tx_3",
        date=now,
        bank_description="Razorpay payout",
        bank_amount=50000,
        rzp_amount=50000,
        delta_amount=0,
        match_status="MATCHED",
        match_tier="TIER_0",
        diagnostic_type="EXACT_MATCH",
        diagnostic_note="Exact match",
        matched_at=now,
    )
    assert item3.bank_amount == Decimal("50000.00")


def test_reconciliation_status_response_rejects_floats():
    with pytest.raises(ValidationError):
        ReconciliationStatusResponse(
            batch_id="batch_1",
            total_records=10,
            matched_count=10,
            suggested_count=0,
            conflict_count=0,
            exception_count=0,
            match_rate_percentage=100.0,
            total_ingested_amount=1000.50,  # float rejected!
            total_reconciled_amount=Decimal("1000.50"),
            total_exception_amount=Decimal("0.00"),
        )

    # Valid construction
    status = ReconciliationStatusResponse(
        batch_id="batch_1",
        total_records=10,
        matched_count=10,
        suggested_count=0,
        conflict_count=0,
        exception_count=0,
        match_rate_percentage=100.0,
        total_ingested_amount=Decimal("1000.50"),
        total_reconciled_amount="1000.50",
        total_exception_amount=0,
    )
    assert status.total_ingested_amount == Decimal("1000.50")


def test_bank_transaction_schemas_reject_floats():
    now = datetime.now(timezone.utc)
    # BankTransactionBase float rejection
    with pytest.raises(ValidationError):
        BankTransactionBase(date=now, amount=1234.56)

    # BankTransactionCreate float rejection
    with pytest.raises(ValidationError):
        BankTransactionCreate(date=now, amount=1234.56, row_hash="h1")

    # BankTransactionResponse float rejection
    with pytest.raises(ValidationError):
        BankTransactionResponse(
            id="bt_1",
            batch_id="b1",
            row_hash="h1",
            date=now,
            amount=1234.56,
            created_at=now,
        )

    # Valid inputs
    tx = BankTransactionBase(date=now, amount=Decimal("1234.56"))
    assert tx.amount == Decimal("1234.56")
    tx_str = BankTransactionBase(date=now, amount="1234.56")
    assert tx_str.amount == Decimal("1234.56")
    tx_int = BankTransactionBase(date=now, amount=1000)
    assert tx_int.amount == Decimal("1000.00")


def test_razorpay_settlement_schemas_reject_floats():
    now = datetime.now(timezone.utc)
    # RazorpaySettlementBase float rejection on amount
    with pytest.raises(ValidationError):
        RazorpaySettlementBase(
            settlement_id="setl_1",
            amount=50000.00,
            settlement_created_at=now,
        )

    # Float rejection on gross_amount
    with pytest.raises(ValidationError):
        RazorpaySettlementBase(
            settlement_id="setl_1",
            amount=Decimal("50000.00"),
            gross_amount=50000.00,
            settlement_created_at=now,
        )

    # Float rejection on fees
    with pytest.raises(ValidationError):
        RazorpaySettlementBase(
            settlement_id="setl_1",
            amount=Decimal("50000.00"),
            fees=762.71,
            settlement_created_at=now,
        )

    # Float rejection on tax
    with pytest.raises(ValidationError):
        RazorpaySettlementBase(
            settlement_id="setl_1",
            amount=Decimal("50000.00"),
            tax=137.29,
            settlement_created_at=now,
        )

    # Valid inputs
    setl = RazorpaySettlementBase(
        settlement_id="setl_1",
        amount=Decimal("49100.00"),
        gross_amount="50000.00",
        fees=762,
        tax=Decimal("137.29"),
        settlement_created_at=now,
    )
    assert setl.amount == Decimal("49100.00")
    assert setl.gross_amount == Decimal("50000.00")
    assert setl.fees == Decimal("762.00")
    assert setl.tax == Decimal("137.29")
