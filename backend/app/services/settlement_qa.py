"""Settlement Q&A Agent Service.

Provides natural language narration of already-computed reconciliation facts.
Strictly auditable, deterministic retrieval, and guarded output.
"""

from datetime import datetime, timezone
from decimal import Decimal
import httpx
from app.core.config import settings
from app.core.logging import logger
from app.models.reconciliation_log import ReconciliationLog
from app.repositories.qa_repo import QaRepository
from app.schemas.qa import QaAskResponse
from app.services.guardrail import validate_qa_narration
from app.utils.money import format_inr, to_decimal


def generate_template_fallback(log: ReconciliationLog) -> str:
    """Deterministic, reliable template fallback explanation when LLM is unavailable or rejected."""
    bank_amt = format_inr(to_decimal(log.bank_transaction.amount)) if log.bank_transaction else "N/A"
    setl_id = log.rzp_settlement.settlement_id if log.rzp_settlement else "Unlinked"
    delta = format_inr(to_decimal(log.delta_amount))

    if log.match_status == "MATCHED":
        fees_amt = to_decimal(log.rzp_settlement.fees) if log.rzp_settlement else Decimal("0.00")
        tax_amt = to_decimal(log.rzp_settlement.tax) if log.rzp_settlement else Decimal("0.00")
        gross_amt = to_decimal(log.rzp_settlement.gross_amount) if log.rzp_settlement else Decimal("0.00")

        if log.diagnostic_type == "TDS_194O_DEDUCTION":
            return (
                f"Settlement {setl_id} reflects 1% Section 194-O TDS deduction on gross e-commerce sales "
                f"in addition to payment gateway fees + 18% GST: {log.diagnostic_note}"
            )
        elif log.diagnostic_type == "BATCHED_SETTLEMENT":
            return (
                f"This bank credit was batched across multiple Razorpay settlements: {log.diagnostic_note}"
            )

        if fees_amt > Decimal("0.00") or tax_amt > Decimal("0.00"):
            fees = format_inr(fees_amt)
            tax = format_inr(tax_amt)
            gross = format_inr(gross_amt)
            return (
                f"Settlement {setl_id} (Gross: {gross}) settled at net payout {bank_amt} "
                f"after Gateway Processing Fee ({fees}) + 18% GST ({tax}). "
                f"Reflected as {log.diagnostic_type}."
            )

        if log.diagnostic_type == "EXACT_MATCH":
            return (
                f"This transaction settled cleanly with an exact match of {bank_amt} "
                f"under settlement {setl_id}. No action is required."
            )
        elif log.diagnostic_type == "FEE_DEDUCTION":
            fees = format_inr(fees_amt)
            tax = format_inr(tax_amt)
            return (
                f"This settlement was short by {delta}. This matches the Gateway Processing Fee "
                f"({fees}) + 18% GST ({tax}). This is already verified as a FEE DEDUCTION."
            )
        elif log.diagnostic_type == "REFUND_ADJUSTED":
            return (
                f"The net settlement payout was adjusted by {delta} due to customer refund "
                f"clawbacks in this settlement cycle for settlement {setl_id}."
            )
        elif log.diagnostic_type == "REVERSAL":
            return (
                f"This is a bank debit of {bank_amt} reflecting a settlement chargeback or reversal."
            )

    elif log.match_status == "SUGGESTED":
        return (
            f"This transaction was flagged as a SUGGESTED match ({log.match_tier}) "
            f"for settlement {setl_id} based on: {log.diagnostic_note} "
            f"Pending human CA approval."
        )

    elif log.match_status == "CONFLICT":
        return (
            f"Settlement {setl_id} matched multiple bank statement rows. "
            f"Both records are locked in CONFLICT state pending manual verification."
        )

    # Exception
    return (
        f"This transaction of {bank_amt} is currently an unresolved EXCEPTION. "
        f"Reason: {log.diagnostic_note}"
    )


class SettlementQaAgent:
    def __init__(self, qa_repo: QaRepository):
        self.qa_repo = qa_repo

    async def answer_query(self, query: str) -> QaAskResponse:
        """Processes natural language CA query with deterministic retrieval and guardrailed narration."""
        clean_query = query.strip()
        now = datetime.now(timezone.utc)

        # 1. Deterministic Retrieval Step
        source_log = await self.qa_repo.find_reconciliation_record(clean_query)

        # If no record found, return deterministic not found response immediately
        if not source_log:
            no_record_msg = "No record found matching that reference. Check the order ID, UTR, or settlement ID and try again."
            await self.qa_repo.log_interaction({
                "reconciliation_log_id": None,
                "query_text": clean_query,
                "raw_llm_output": "",
                "final_response": no_record_msg,
                "guardrail_rejected": False,
                "asked_at": now,
            })
            return QaAskResponse(
                query=clean_query,
                answer=no_record_msg,
                source_record_id=None,
                guardrail_rejected=False,
                retrieved_data=None,
                asked_at=now,
            )

        # 2. Narration Step
        raw_llm_output = ""
        guardrail_rejected = False
        final_response = ""

        # Check if LLM API is configured
        if settings.LLM_API_KEY:
            try:
                raw_llm_output = await self._call_llm_narration(clean_query, source_log)
                is_valid, invented_tokens = validate_qa_narration(raw_llm_output, source_log)
                if not is_valid:
                    logger.warning(
                        "qa_guardrail_rejected_invented_numbers",
                        invented_tokens=invented_tokens,
                        query=clean_query,
                    )
                    guardrail_rejected = True
                    final_response = generate_template_fallback(source_log)
                else:
                    final_response = raw_llm_output
            except Exception as e:
                logger.error("qa_llm_call_failed", error=str(e))
                final_response = generate_template_fallback(source_log)
        else:
            # High-fidelity deterministic narration fallback
            final_response = generate_template_fallback(source_log)
            raw_llm_output = final_response

        # 3. Log Interaction Audit Record
        await self.qa_repo.log_interaction({
            "reconciliation_log_id": source_log.id,
            "query_text": clean_query,
            "raw_llm_output": raw_llm_output,
            "final_response": final_response,
            "guardrail_rejected": guardrail_rejected,
            "asked_at": now,
        })

        retrieved_data = {
            "match_status": source_log.match_status,
            "match_tier": source_log.match_tier,
            "diagnostic_type": source_log.diagnostic_type,
            "delta_amount": str(source_log.delta_amount),
            "diagnostic_note": source_log.diagnostic_note,
            "bank_amount": str(source_log.bank_transaction.amount) if source_log.bank_transaction else None,
            "bank_utr": source_log.bank_transaction.utr if source_log.bank_transaction else None,
            "settlement_id": source_log.rzp_settlement.settlement_id if source_log.rzp_settlement else None,
        }

        return QaAskResponse(
            query=clean_query,
            answer=final_response,
            source_record_id=source_log.id,
            source_settlement_id=source_log.rzp_settlement.settlement_id if source_log.rzp_settlement else None,
            source_bank_utr=source_log.bank_transaction.utr if source_log.bank_transaction else None,
            guardrail_rejected=guardrail_rejected,
            retrieved_data=retrieved_data,
            asked_at=now,
        )

    async def _call_llm_narration(self, query: str, log: ReconciliationLog) -> str:
        """Invokes external LLM to narrate facts strictly without computing."""
        prompt = (
            "You are ReconGrid AI's Settlement Explainer for Chartered Accountants.\n"
            "Explain this existing computed reconciliation result in clear, professional language.\n"
            "CRITICAL RULE: Do NOT perform math, do NOT estimate, do NOT invent any numbers.\n"
            f"Record Details:\n"
            f"- Status: {log.match_status}\n"
            f"- Tier: {log.match_tier}\n"
            f"- Diagnostic Type: {log.diagnostic_type}\n"
            f"- Delta: {log.delta_amount}\n"
            f"- Note: {log.diagnostic_note}\n"
            f"- Bank Amount: {log.bank_transaction.amount if log.bank_transaction else 'N/A'}\n"
            f"- Settlement ID: {log.rzp_settlement.settlement_id if log.rzp_settlement else 'N/A'}\n"
            f"- Question: {query}\n"
        )
        # Call provider via httpx (compatible with standard chat completions / anthropic endpoints)
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.LLM_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": settings.LLM_MODEL,
                    "max_tokens": 300,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                return data["content"][0]["text"].strip()
            raise RuntimeError(f"LLM API error: {resp.status_code} {resp.text}")
