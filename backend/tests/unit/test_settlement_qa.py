"""Unit tests for Settlement Q&A Agent and template fallback generation."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.core.config import settings
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.models.reconciliation_log import ReconciliationLog
from app.services.settlement_qa import SettlementQaAgent, generate_template_fallback


def test_generate_template_fallback_branches():
    now = datetime.now(timezone.utc)
    bank = BankTransaction(
        id="bank_1",
        row_hash="h1",
        date=now,
        amount=Decimal("49100.00"),
        direction="CREDIT",
        utr="CMS123456",
        description="CMS/123456/PAYOUT",
    )
    rzp = RazorpaySettlement(
        id="rzp_1",
        settlement_id="setl_123",
        amount=Decimal("49100.00"),
        gross_amount=Decimal("50000.00"),
        fees=Decimal("762.71"),
        tax=Decimal("137.29"),
        utr="CMS123456",
        settlement_created_at=now,
    )

    # 1. TDS_194O_DEDUCTION
    log_tds = ReconciliationLog(
        id="l1",
        bank_tx_id="bank_1",
        match_status="MATCHED",
        match_tier="TIER_3",
        delta_amount=Decimal("1900.00"),
        diagnostic_type="TDS_194O_DEDUCTION",
        diagnostic_note="Matched 1% TDS",
        bank_transaction=bank,
        rzp_settlement=rzp,
        matched_at=now,
    )
    text = generate_template_fallback(log_tds)
    assert "Section 194-O TDS" in text

    # 2. BATCHED_SETTLEMENT
    log_batched = ReconciliationLog(
        id="l2",
        bank_tx_id="bank_1",
        match_status="MATCHED",
        match_tier="TIER_3",
        delta_amount=Decimal("0.00"),
        diagnostic_type="BATCHED_SETTLEMENT",
        diagnostic_note="Batched across 2 settlements",
        bank_transaction=bank,
        rzp_settlement=rzp,
        matched_at=now,
    )
    text = generate_template_fallback(log_batched)
    assert "batched across multiple Razorpay settlements" in text

    # 3. EXACT_MATCH without fees/tax
    rzp_zero_fees = RazorpaySettlement(
        id="rzp_zero",
        settlement_id="setl_zero",
        amount=Decimal("50000.00"),
        gross_amount=Decimal("50000.00"),
        fees=Decimal("0.00"),
        tax=Decimal("0.00"),
        settlement_created_at=now,
    )
    log_exact = ReconciliationLog(
        id="l3",
        bank_tx_id="bank_1",
        match_status="MATCHED",
        match_tier="TIER_1",
        delta_amount=Decimal("0.00"),
        diagnostic_type="EXACT_MATCH",
        diagnostic_note="Exact match",
        bank_transaction=bank,
        rzp_settlement=rzp_zero_fees,
        matched_at=now,
    )
    text = generate_template_fallback(log_exact)
    assert "settled cleanly with an exact match" in text

    # 4. FEE_DEDUCTION without fees/tax on settlement model
    log_fee = ReconciliationLog(
        id="l4",
        bank_tx_id="bank_1",
        match_status="MATCHED",
        match_tier="TIER_3",
        delta_amount=Decimal("900.00"),
        diagnostic_type="FEE_DEDUCTION",
        diagnostic_note="Fee deduction",
        bank_transaction=bank,
        rzp_settlement=rzp_zero_fees,
        matched_at=now,
    )
    text = generate_template_fallback(log_fee)
    assert "short by" in text and "FEE DEDUCTION" in text

    # 5. REFUND_ADJUSTED without fees/tax
    log_refund = ReconciliationLog(
        id="l5",
        bank_tx_id="bank_1",
        match_status="MATCHED",
        match_tier="TIER_3",
        delta_amount=Decimal("5000.00"),
        diagnostic_type="REFUND_ADJUSTED",
        diagnostic_note="Refund clawback",
        bank_transaction=bank,
        rzp_settlement=rzp_zero_fees,
        matched_at=now,
    )
    text = generate_template_fallback(log_refund)
    assert "customer refund clawbacks" in text

    # 6. REVERSAL without fees/tax
    log_reversal = ReconciliationLog(
        id="l6",
        bank_tx_id="bank_1",
        match_status="MATCHED",
        match_tier="TIER_3",
        delta_amount=Decimal("15000.00"),
        diagnostic_type="REVERSAL",
        diagnostic_note="Reversal",
        bank_transaction=bank,
        rzp_settlement=rzp_zero_fees,
        matched_at=now,
    )
    text = generate_template_fallback(log_reversal)
    assert "settlement chargeback or reversal" in text

    # 7. SUGGESTED
    log_sugg = ReconciliationLog(
        id="l7",
        bank_tx_id="bank_1",
        match_status="SUGGESTED",
        match_tier="TIER_2",
        delta_amount=Decimal("0.00"),
        diagnostic_type="FUZZY_MATCH",
        diagnostic_note="Fuzzy matched with 0.92 score",
        bank_transaction=bank,
        rzp_settlement=rzp,
        matched_at=now,
    )
    text = generate_template_fallback(log_sugg)
    assert "flagged as a SUGGESTED match" in text

    # 8. CONFLICT
    log_conflict = ReconciliationLog(
        id="l8",
        bank_tx_id="bank_1",
        match_status="CONFLICT",
        match_tier="TIER_1",
        delta_amount=Decimal("0.00"),
        diagnostic_type="EXACT_MATCH",
        diagnostic_note="Multiple matches",
        bank_transaction=bank,
        rzp_settlement=rzp,
        matched_at=now,
    )
    text = generate_template_fallback(log_conflict)
    assert "CONFLICT state" in text

    # 9. EXCEPTION
    log_exc = ReconciliationLog(
        id="l9",
        bank_tx_id="bank_1",
        match_status="EXCEPTION",
        match_tier="TIER_3",
        delta_amount=Decimal("900.00"),
        diagnostic_type="UNRESOLVED",
        diagnostic_note="Unexplained variance",
        bank_transaction=bank,
        rzp_settlement=rzp,
        matched_at=now,
    )
    text = generate_template_fallback(log_exc)
    assert "unresolved EXCEPTION" in text

    # 10. Missing bank / rzp relationships
    log_bare = ReconciliationLog(
        id="l10",
        bank_tx_id="b_none",
        match_status="EXCEPTION",
        match_tier="TIER_3",
        delta_amount=Decimal("0.00"),
        diagnostic_type="UNRESOLVED",
        diagnostic_note="No relations",
        matched_at=now,
    )
    text = generate_template_fallback(log_bare)
    assert "N/A" in text


@pytest.mark.asyncio
async def test_qa_agent_not_found():
    repo = AsyncMock()
    repo.find_reconciliation_record.return_value = None
    agent = SettlementQaAgent(repo)

    res = await agent.answer_query("order #999999")
    assert "No record found" in res.answer
    assert res.source_record_id is None
    assert res.guardrail_rejected is False
    repo.log_interaction.assert_awaited_once()


@pytest.mark.asyncio
async def test_qa_agent_with_llm_approved():
    now = datetime.now(timezone.utc)
    bank = BankTransaction(
        id="b1",
        amount=Decimal("49100.00"),
        date=now,
        direction="CREDIT",
        utr="CMS123456",
        description="CMS/123456",
        row_hash="h1",
    )
    rzp = RazorpaySettlement(
        id="r1",
        settlement_id="setl_123",
        amount=Decimal("49100.00"),
        gross_amount=Decimal("50000.00"),
        fees=Decimal("762.71"),
        tax=Decimal("137.29"),
        utr="CMS123456",
        settlement_created_at=now,
    )
    log = ReconciliationLog(
        id="l1",
        bank_tx_id="b1",
        rzp_settlement_id="r1",
        match_status="MATCHED",
        match_tier="TIER_3",
        delta_amount=Decimal("900.00"),
        diagnostic_type="FEE_DEDUCTION",
        diagnostic_note="Difference of ₹ 900.00 matches Gateway Fee (₹ 762.71) + 18% GST (₹ 137.29).",
        bank_transaction=bank,
        rzp_settlement=rzp,
        matched_at=now,
    )

    repo = AsyncMock()
    repo.find_reconciliation_record.return_value = log
    agent = SettlementQaAgent(repo)

    with patch.object(settings, "LLM_API_KEY", "test_key"):
        with patch.object(
            agent,
            "_call_llm_narration",
            AsyncMock(return_value="Settlement setl_123 of 50000.00 net 49100.00 with fee 762.71 and tax 137.29."),
        ):
            res = await agent.answer_query("order #123456")
            assert res.guardrail_rejected is False
            assert "setl_123" in res.answer
            assert res.source_record_id == "l1"


@pytest.mark.asyncio
async def test_qa_agent_with_llm_hallucination_rejected():
    now = datetime.now(timezone.utc)
    bank = BankTransaction(
        id="b1",
        amount=Decimal("49100.00"),
        date=now,
        direction="CREDIT",
        utr="CMS123456",
        description="CMS/123456",
        row_hash="h1",
    )
    log = ReconciliationLog(
        id="l1",
        bank_tx_id="b1",
        match_status="EXCEPTION",
        match_tier="TIER_3",
        delta_amount=Decimal("900.00"),
        diagnostic_type="UNRESOLVED",
        diagnostic_note="Unresolved exception",
        bank_transaction=bank,
        matched_at=now,
    )

    repo = AsyncMock()
    repo.find_reconciliation_record.return_value = log
    agent = SettlementQaAgent(repo)

    with patch.object(settings, "LLM_API_KEY", "test_key"):
        # Hallucinating 9999999.00 which is not in record
        with patch.object(
            agent,
            "_call_llm_narration",
            AsyncMock(return_value="Your balance was short by 9999999.00 due to unknown charge."),
        ):
            res = await agent.answer_query("order #123456")
            assert res.guardrail_rejected is True
            # Fell back to template
            assert "unresolved EXCEPTION" in res.answer


@pytest.mark.asyncio
async def test_qa_agent_with_llm_api_failure():
    now = datetime.now(timezone.utc)
    bank = BankTransaction(
        id="b1",
        amount=Decimal("49100.00"),
        date=now,
        direction="CREDIT",
        utr="CMS123456",
        description="CMS/123456",
        row_hash="h1",
    )
    log = ReconciliationLog(
        id="l1",
        bank_tx_id="b1",
        match_status="EXCEPTION",
        match_tier="TIER_3",
        delta_amount=Decimal("900.00"),
        diagnostic_type="UNRESOLVED",
        diagnostic_note="Unresolved exception",
        bank_transaction=bank,
        matched_at=now,
    )

    repo = AsyncMock()
    repo.find_reconciliation_record.return_value = log
    agent = SettlementQaAgent(repo)

    with patch.object(settings, "LLM_API_KEY", "test_key"):
        with patch.object(
            agent,
            "_call_llm_narration",
            AsyncMock(side_effect=RuntimeError("LLM API 500 Internal Error")),
        ):
            res = await agent.answer_query("order #123456")
            assert "unresolved EXCEPTION" in res.answer


@pytest.mark.asyncio
async def test_call_llm_narration_live_mock():
    agent = SettlementQaAgent(AsyncMock())
    now = datetime.now(timezone.utc)
    log = ReconciliationLog(
        id="l1",
        bank_tx_id="b1",
        match_status="MATCHED",
        match_tier="TIER_1",
        delta_amount=Decimal("0.00"),
        diagnostic_type="EXACT_MATCH",
        diagnostic_note="Exact match",
        matched_at=now,
    )

    # 1. NVIDIA NIM / OpenAI 200 response
    mock_resp_nvidia = MagicMock()
    mock_resp_nvidia.status_code = 200
    mock_resp_nvidia.json.return_value = {"choices": [{"message": {"content": "Explained via NVIDIA NIM."}}]}

    with patch.object(settings, "LLM_PROVIDER", "nvidia"):
        with patch.object(settings, "LLM_BASE_URL", "https://integrate.api.nvidia.com/v1"):
            with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp_nvidia)):
                text = await agent._call_llm_narration("Why did this settle?", log)
                assert text == "Explained via NVIDIA NIM."

    # 2. Anthropic 200 response
    mock_resp_anthropic = MagicMock()
    mock_resp_anthropic.status_code = 200
    mock_resp_anthropic.json.return_value = {"content": [{"text": "Explained via Anthropic."}]}

    with patch.object(settings, "LLM_PROVIDER", "anthropic"):
        with patch.object(settings, "LLM_BASE_URL", ""):
            with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp_anthropic)):
                text = await agent._call_llm_narration("Why did this settle?", log)
                assert text == "Explained via Anthropic."

    # 3. Non-200 error response
    mock_err_resp = MagicMock()
    mock_err_resp.status_code = 401
    mock_err_resp.text = "Unauthorized"

    with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_err_resp)):
        with pytest.raises(RuntimeError) as exc_info:
            await agent._call_llm_narration("Why did this settle?", log)
        assert "LLM API error: 401" in str(exc_info.value)
