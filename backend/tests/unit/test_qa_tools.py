"""Unit tests for the Settlement Q&A tool registry: intent parsing and deterministic tools."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.models.reconciliation_log import ReconciliationLog
from app.services.settlement_qa import (
    SettlementQaAgent,
    audit_trial_balance_tool,
    explain_diagnostic_tool,
    get_batch_summary_tool,
    inspect_record_tool,
    parse_query,
    route_query,
)

SUMMARY = {
    "total_records": 40,
    "matched_count": 30,
    "suggested_count": 4,
    "conflict_count": 1,
    "exception_count": 5,
    "match_rate_percentage": 75.0,
    "total_ingested_amount": "1000000.00",
    "total_reconciled_amount": "800000.00",
    "total_suggested_amount": "60000.00",
    "total_conflict_amount": "10000.00",
    "total_pending_amount": "30000.00",
    "total_exception_amount": "100000.00",
    "total_unresolved_variance": "100000.00",
    "is_in_balance": False,
}


def make_log(diagnostic="FEE_DEDUCTION", utr="ICIC009283"):
    now = datetime.now(UTC)
    bank = BankTransaction(
        id="b1", amount=Decimal("49100.00"), date=now, direction="CREDIT",
        utr=utr, description="CMS/PAYOUT", row_hash="h1",
    )
    rzp = RazorpaySettlement(
        id="r1", settlement_id="setl_abc123", amount=Decimal("49100.00"),
        gross_amount=Decimal("50000.00"), fees=Decimal("762.71"), tax=Decimal("137.29"),
        utr=utr, settlement_created_at=now,
    )
    return ReconciliationLog(
        id="l1", bank_tx_id="b1", rzp_settlement_id="r1", match_status="MATCHED",
        match_tier="TIER_3", delta_amount=Decimal("0.00"), diagnostic_type=diagnostic,
        diagnostic_note="note", bank_transaction=bank, rzp_settlement=rzp, matched_at=now,
    )


@pytest.mark.parametrize(
    "query, intent",
    [
        ("Breakdown fees for UTR ICIC009283", "inspect_record"),
        ("what GST was charged on setl_abc123?", "inspect_record"),
        ("how much TDS was cut from CMS002938491801", "inspect_record"),
        ("is my trial balance in balance?", "audit_trial_balance"),
        ("what is the total variance right now", "audit_trial_balance"),
        ("do the books tally", "audit_trial_balance"),
        ("why is there a mismatch", "audit_trial_balance"),
        ("give me a batch summary", "get_batch_summary"),
        ("how many were matched", "get_batch_summary"),
        ("why do I see FEE_DEDUCTION", "explain_diagnostic"),
        ("what does a batched settlement mean", "explain_diagnostic"),
        ("explain refund adjusted", "explain_diagnostic"),
        ("hello there", None),
    ],
)
def test_parse_query_intents(query, intent):
    assert parse_query(query).intent == intent


def test_parse_query_extracts_entities():
    parsed = parse_query("Breakdown fees for UTR ICIC009283 under setl_abc123")
    assert parsed.utr == "ICIC009283"
    assert parsed.settlement_id == "setl_abc123"


def test_inspect_record_tool_returns_exact_values():
    result = inspect_record_tool(make_log())
    assert result.tool == "inspect_record_tool"
    assert result.data["fee"] == "762.71"
    assert result.data["gst"] == "137.29"
    assert result.data["tds"] == "0.00"
    assert result.data["net"] == "49100.00"
    assert "Net = Gross - Fee - GST - TDS - Refunds" in result.answer


def test_inspect_record_tool_includes_tds_when_diagnosed():
    result = inspect_record_tool(make_log(diagnostic="TDS_194O_DEDUCTION"))
    assert result.data["tds"] == "500.00"
    assert result.data["net"] == "48600.00"


def test_trial_balance_reports_live_numbers():
    result = audit_trial_balance_tool(SUMMARY)
    assert result.data["is_in_balance"] is False
    assert result.data["total_unresolved_variance"] == "100000.00"
    assert result.data["bucket_sum"] == "1000000.00"


def test_trial_balance_without_summary_produces_nothing():
    assert audit_trial_balance_tool(None) is None
    assert get_batch_summary_tool(None) is None


def test_batch_summary_uses_summary_counts():
    result = get_batch_summary_tool(SUMMARY)
    assert "30" in result.answer and "75.0%" in result.answer


def test_explain_diagnostic_known_and_unknown():
    assert "gateway fee" in explain_diagnostic_tool("FEE_DEDUCTION").answer
    assert explain_diagnostic_tool("NOPE") is None
    assert explain_diagnostic_tool(None) is None


def test_route_query_picks_tool_without_record():
    assert route_query(parse_query("is the trial balance in balance"), SUMMARY).tool == "audit_trial_balance_tool"
    assert route_query(parse_query("what does REVERSAL mean"), None).tool == "explain_diagnostic_tool"
    assert route_query(parse_query("hello"), SUMMARY) is None


async def test_agent_runs_inspect_tool_for_utr_fee_question():
    repo = AsyncMock()
    repo.find_reconciliation_record.return_value = make_log()
    response = await SettlementQaAgent(repo).answer_query("Breakdown fees for UTR ICIC009283")
    assert response.retrieved_data["tool"] == "inspect_record_tool"
    assert "762.71" in response.answer and "137.29" in response.answer
    assert response.source_record_id == "l1"
    repo.log_interaction.assert_awaited_once()


async def test_agent_runs_explain_tool_without_record():
    repo = AsyncMock()
    repo.find_reconciliation_record.return_value = None
    response = await SettlementQaAgent(repo).answer_query("what does REVERSAL mean")
    assert response.retrieved_data["tool"] == "explain_diagnostic_tool"
    assert response.source_record_id is None


def test_inspect_record_subtracts_refunds_from_net():
    log = make_log("REFUND_ADJUSTED")
    log.rzp_settlement.raw_payload = {"refund_total": "5000.00"}
    result = inspect_record_tool(log)
    assert result.data["refund"] == "5000.00"
    assert result.data["net"] == "44100.00"


def test_inspect_record_counts_tds_on_compound_matches():
    log = make_log("REFUND_ADJUSTED")
    log.diagnostic_note = "refund clawback + 1% TDS (₹ 500.00) + gateway fee"
    result = inspect_record_tool(log)
    assert result.data["tds"] == "500.00"


def test_inspect_record_unlinked_does_not_invent_zero_fees():
    log = make_log("UNRESOLVED")
    log.rzp_settlement = None
    result = inspect_record_tool(log)
    assert "unavailable" in result.answer
    assert "fee" not in result.data


@pytest.mark.parametrize("diagnostic", ["FX_ADJUSTED", "PENDING_SETTLEMENT"])
def test_emitted_diagnostics_have_explanations(diagnostic):
    parsed = parse_query(f"what does {diagnostic} mean")
    assert parsed.diagnostic_type == diagnostic
    assert explain_diagnostic_tool(diagnostic) is not None


def test_batch_summary_lists_pending_bucket():
    result = get_batch_summary_tool({"total_records": 5, "pending_count": 2})
    assert "In-transit" in result.answer and ": 2" in result.answer
