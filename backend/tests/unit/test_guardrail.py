"""Unit tests for the Settlement Q&A Numeric Token Guardrail."""

from datetime import datetime, timezone
from decimal import Decimal
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.models.reconciliation_log import ReconciliationLog
from app.services.guardrail import extract_numeric_tokens, validate_qa_narration


def test_extract_numeric_tokens():
    text = "Order #4521 was short by Rs 900.00 due to fee Rs 762.71 + 18% GST (Rs 137.29)."
    tokens = extract_numeric_tokens(text)
    assert "4521" in tokens
    assert "900" in tokens or "900.00" in tokens
    assert "762.71" in tokens
    assert "137.29" in tokens
    assert "18" in tokens or "18.00" in tokens


def test_guardrail_passes_valid_narration():
    bank = BankTransaction(
        id="bank_1",
        row_hash="hash_1",
        date=datetime(2026, 8, 24, tzinfo=timezone.utc),
        amount=Decimal("49100.00"),
        direction="CREDIT",
        utr="CMS002938491805",
        description="CMS/002938491805/RAZORPAY ORDER 4521",
    )
    rzp = RazorpaySettlement(
        id="rzp_1",
        settlement_id="setl_Kjs9283jkd905",
        amount=Decimal("49100.00"),
        gross_amount=Decimal("50000.00"),
        fees=Decimal("762.71"),
        tax=Decimal("137.29"),
        utr="CMS002938491805",
    )
    log = ReconciliationLog(
        id="log_1",
        bank_tx_id="bank_1",
        rzp_settlement_id="rzp_1",
        match_status="MATCHED",
        match_tier="TIER_3",
        delta_amount=Decimal("900.00"),
        diagnostic_type="FEE_DEDUCTION",
        diagnostic_note="Difference of ₹ 900.00 matches Gateway Fee (₹ 762.71) + 18% GST (₹ 137.29).",
        bank_transaction=bank,
        rzp_settlement=rzp,
    )

    valid_text = (
        "Order 4521 settlement had a gross amount of 50000.00 and net 49100.00. "
        "The difference of 900.00 matches fee 762.71 plus 18% GST 137.29."
    )
    is_valid, invented = validate_qa_narration(valid_text, log)
    assert is_valid is True
    assert len(invented) == 0


def test_guardrail_rejects_hallucinated_numbers():
    bank = BankTransaction(
        id="bank_1",
        row_hash="hash_1",
        date=datetime(2026, 8, 24, tzinfo=timezone.utc),
        amount=Decimal("49100.00"),
        direction="CREDIT",
        utr="CMS002938491805",
        description="CMS/002938491805",
    )
    log = ReconciliationLog(
        id="log_1",
        bank_tx_id="bank_1",
        match_status="EXCEPTION",
        match_tier="TIER_3",
        delta_amount=Decimal("900.00"),
        diagnostic_type="UNRESOLVED",
        diagnostic_note="Unresolved exception",
        bank_transaction=bank,
    )

    # Text containing invented number 99999.00 and 777.00
    hallucinated_text = "I believe your bank received 99999.00 with fee 777.00."
    is_valid, invented = validate_qa_narration(hallucinated_text, log)
    assert is_valid is False
    assert any("99999" in token for token in invented)


def test_guardrail_rejects_fabricated_gst_claim():
    from types import SimpleNamespace
    fake_log = SimpleNamespace(
        delta_amount=Decimal('900.00'),
        confidence_score=0.60,
        bank_transaction=None,
        rzp_settlement=None,
        diagnostic_note='Fee deduction matched within tolerance.',
    )
    narration = 'This is explained by an 18% GST-only adjustment, unrelated to the actual fee.'
    is_valid, invented = validate_qa_narration(narration, fake_log)
    assert is_valid is False, f"Guardrail still lets fabricated GST claims through: {invented}"

