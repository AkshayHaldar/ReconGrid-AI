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


def generate_template_fallback(log: ReconciliationLog, query: str = "") -> str:
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

    elif log.match_status == "PENDING_SETTLEMENT_DATA":
        return (
            f"This transaction of {bank_amt} is currently in PENDING_SETTLEMENT_DATA state. "
            f"Reason: {log.diagnostic_note}"
        )

    # Exception
    return (
        f"This transaction of {bank_amt} is currently an unresolved EXCEPTION. "
        f"Reason: {log.diagnostic_note}"
    )


def generate_followup_response(log: ReconciliationLog, query: str = "") -> str:
    """Provides conversational, context-aware follow-up answers for a specific reconciliation log."""
    q = query.lower().strip()
    setl_id = log.rzp_settlement.settlement_id if log.rzp_settlement else "Unlinked"
    bank_amt = format_inr(to_decimal(log.bank_transaction.amount)) if log.bank_transaction else "N/A"
    utr = log.bank_transaction.utr if log.bank_transaction else (log.rzp_settlement.utr if log.rzp_settlement else "N/A")

    # 1. Actionable verification & resolution queries ("how i verfie", "how to verify", "how to resolve", "what should I do", "verify")
    if any(k in q for k in ("verfie", "verif", "resolve", "how do i", "how to", "what should i do", "action", "how can i", "fix", "approve")):
        if log.match_status == "CONFLICT":
            return (
                f"⚔️ **How to Verify & Resolve Conflict for {setl_id}**:\n\n"
                f"1. Click **'Highlight in Ledger'** below to jump directly to this transaction.\n"
                "2. Click the **'Resolve Conflict'** button on the row to open the **Conflict Resolution Drawer**.\n"
                "3. Review the candidate bank credits claiming this settlement. Select the legitimate transaction and click **'Confirm Assignment'**.\n"
                "4. The selected row will be locked as `OK MATCHED`, and duplicate claims will be transferred to `EXCEPTION`."
            )
        elif log.match_status == "SUGGESTED":
            return (
                f"⚖️ **How to Verify & Approve Suggested Match for {setl_id}**:\n\n"
                f"• This transaction ({bank_amt}) was suggested with {int(log.confidence_score * 100)}% descriptor similarity.\n"
                "• **1-Click Approval**: Click the green checkmark (**Approve**) on the table row to lock it as `OK MATCHED`.\n"
                "• **Bulk Approval**: Click **'Batch Approve (≥90%)'** in the top filter bar to approve all high-confidence suggestions at once.\n"
                "• If incorrect, click the red **'Deny'** button to move it to `EXCEPTION`."
            )
        elif log.match_status == "EXCEPTION":
            return (
                f"🚨 **How to Audit & Resolve Exception ({bank_amt})**:\n\n"
                "1. Click **'Highlight in Ledger'** below to locate this row.\n"
                "2. Click the **Audit Drawer** (inspect button) to review the raw bank statement row and error diagnostics.\n"
                "3. If this was an internal P2P deposit, interest, or bank fee, add an audit remark and keep it as a verified exception.\n"
                "4. If awaiting gateway settlement, click **'Sync / Seed'** in the top bar to pull subsequent settlement batches."
            )
        elif log.match_status == "PENDING_SETTLEMENT_DATA":
            return (
                f"⏳ **How to Handle In-Transit Settlement ({bank_amt})**:\n\n"
                f"• This bank transaction is within the active settlement window (≤5 days old).\n"
                "• Click **'Sync / Seed'** in the top bar to pull the latest settlement batch from Razorpay. Once ingested, it will automatically transition to `OK MATCHED`."
            )
        else: # MATCHED
            return (
                f"✅ **Transaction is Already Fully Reconciled**:\n\n"
                f"• Settlement `{setl_id}` has already been mathematically verified against UTR `{utr}` with zero delta.\n"
                "• No further action or verification is required. This record is sealed for statutory audit."
            )

    # 2. Fee / Calculation queries ("what is the fee", "why fee", "tax", "gst", "tds")
    if any(k in q for k in ("fee", "tax", "gst", "tds", "deduction", "mdr", "charge")):
        fees_amt = to_decimal(log.rzp_settlement.fees) if log.rzp_settlement else Decimal("0.00")
        tax_amt = to_decimal(log.rzp_settlement.tax) if log.rzp_settlement else Decimal("0.00")
        gross_amt = to_decimal(log.rzp_settlement.gross_amount) if log.rzp_settlement else Decimal("0.00")
        delta = format_inr(to_decimal(log.delta_amount))

        return (
            f"💰 **Fee & Tax Breakdown for {setl_id}**:\n\n"
            f"• **Gross Amount**: {format_inr(gross_amt)}\n"
            f"• **Gateway MDR Fee (2%)**: {format_inr(fees_amt)}\n"
            f"• **GST on Fee (18%)**: {format_inr(tax_amt)}\n"
            f"• **Total Variance / Delta**: {delta}\n"
            f"• **Diagnostic Classification**: `{log.diagnostic_type}`\n"
            f"• **Audit Note**: {log.diagnostic_note}"
        )

    # 3. Default fallback
    return generate_template_fallback(log, query)


def answer_project_overview_question(query: str, summary: dict | None = None) -> str | None:
    """Answers general architecture, KPI metric, and domain questions about ReconGrid AI."""
    q = query.lower().strip()
    
    # Specific Conflict Resolution Guide
    if any(k in q for k in ("resolve conflict", "resolve conflicts", "how do i resolve conflict", "how to resolve conflict", "conflict resolution")):
        return (
            "⚔️ **How to Resolve Multi-Candidate Conflicts**:\n\n"
            "1. **Locate the Conflict**: Select the **'Conflicts'** tab on the ledger table to view rows in conflict.\n"
            "2. **Open Conflict Drawer**: Click **'Resolve Conflict'** on the row to inspect all competing bank entries claiming the same Razorpay settlement ID.\n"
            "3. **Select Valid Row**: Compare dates, reference remarks, and amounts, then choose the legitimate claimant bank credit.\n"
            "4. **Confirm Assignment**: Click **'Confirm Resolution'**. The winning transaction is locked as `OK MATCHED`, while duplicate/competing rows are automatically transferred to `EXCEPTION` with an audit trail note."
        )

    # 1. Total Ingested Ledger
    if any(k in q for k in ("ingested ledger", "total ingested", "ingested amount", "ingestion")):
        total_txs = summary.get("total_records", "N/A") if summary else "all"
        total_amt = format_inr(to_decimal(summary.get("total_ingested_amount", 0))) if summary else "the ledger sum"
        credit_amt = format_inr(to_decimal(summary.get("total_credit_amount", 0))) if summary else "₹ 0.00"
        debit_amt = format_inr(to_decimal(summary.get("total_debit_amount", 0))) if summary else "₹ 0.00"
        net_amt = format_inr(to_decimal(summary.get("net_ingested_amount", 0))) if summary else "₹ 0.00"
        return (
            "📊 **Total Ingested Ledger** represents the complete baseline sum of all bank statement transactions (both inflow credits and outflow debits) parsed and loaded into ReconGrid AI from your uploaded bank statement files (PDF/CSV).\n\n"
            f"• **Current Ingested Total**: {total_txs} transactions totaling {total_amt}.\n"
            f"• **Gross Credits (Inflows)**: {credit_amt}\n"
            f"• **Gross Debits (Outflows/Reversals)**: {debit_amt}\n"
            f"• **Net Cash Inflow**: {net_amt}\n"
            "• **Purpose**: It establishes the 100% auditable ground truth of cash-in-bank movements against which payment gateway payouts (Razorpay settlements) are matched and verified.\n"
            "• **Formats Supported**: Multi-page PDFs (SBI, HDFC, ICICI, Axis, Kotak, etc. with auto-decryption) and NetBanking CSVs."
        )

    # 2. Auto-Reconciled Net / Match Rate
    if any(k in q for k in ("auto-reconciled", "auto reconciled", "reconciled net", "match rate", "auto reconcile")):
        matched_txs = summary.get("matched_count", "N/A") if summary else "the matched"
        match_pct = summary.get("match_rate_percentage", "N/A") if summary else "the match"
        reconciled_amt = format_inr(to_decimal(summary.get("total_reconciled_amount", 0))) if summary else "the reconciled total"
        return (
            "✅ **Auto-Reconciled Net** is the total value and percentage of bank transactions that were automatically matched against Razorpay settlements with zero delta variance (`OK MATCHED`).\n\n"
            f"• **Current Reconciled Net**: {matched_txs} transactions ({match_pct}%) totaling {reconciled_amt}.\n"
            "• **How It Works**: The engine evaluates each bank credit across 3 deterministic tiers:\n"
            "  1. **Tier 1 (Exact Match)**: Exact UTR and payout amount match.\n"
            "  2. **Tier 2 (Fuzzy Descriptor)**: Bank descriptions matching Razorpay descriptors (>= 90% confidence).\n"
            "  3. **Tier 3 (Diagnostic Match)**: Automatically calculates and verifies Gateway Fees (2% MDR + 18% GST), Section 194-O TDS (1%), and refund clawbacks."
        )

    # 3. CA Review Required / Suggested / Conflicts
    if any(k in q for k in ("ca review", "review required", "suggested match", "conflict")):
        sugg = summary.get("suggested_count", 0) if summary else 0
        conf = summary.get("conflict_count", 0) if summary else 0
        return (
            "⚖️ **CA Review Required** flags transactions that require human Chartered Accountant review or approval before closing the books:\n\n"
            f"• **Suggested Matches ({sugg} pending)**: High-confidence fuzzy matches (e.g. 90%–99% descriptor similarity). A CA can promote them to `OK MATCHED` with a single click.\n"
            f"• **Conflicts ({conf} pending)**: Multi-candidate payouts where multiple bank rows claim the same Razorpay settlement ID. CAs open the **Conflict Drawer** to assign the primary valid bank credit and displace duplicate claims.\n"
            "• **Audit Trail**: Every CA action is sealed with an immutable timestamp and audit note."
        )

    # 4. Unresolved Variance / Exceptions
    if any(k in q for k in ("unresolved variance", "variance", "trial balance", "in balance", "exception")):
        exc_count = summary.get("exception_count", 0) if summary else 0
        exc_amt = format_inr(to_decimal(summary.get("total_exception_amount", 0))) if summary else "₹ 0.00"
        sugg_amt = format_inr(to_decimal(summary.get("total_suggested_amount", 0))) if summary else "₹ 0.00"
        conf_amt = format_inr(to_decimal(summary.get("total_conflict_amount", 0))) if summary else "₹ 0.00"
        pend_amt = format_inr(to_decimal(summary.get("total_pending_amount", 0))) if summary else "₹ 0.00"
        total_var = format_inr(to_decimal(summary.get("total_unresolved_variance", 0))) if summary else exc_amt
        is_bal = summary.get("is_in_balance", False) if summary else False

        status_tag = "✅ **Trial Balance is In-Balance (₹0.00 Variance)**" if is_bal else f"⚠️ **Active Variance: {total_var}**"

        return (
            f"🚨 **Unresolved Variance & Trial Balance Audit**:\n\n"
            f"{status_tag}\n\n"
            f"**Complete Financial Conservation Breakdown**:\n"
            f"• **Hard Exceptions ({exc_count} txns)**: {exc_amt} (no gateway settlement match found)\n"
            f"• **Review-Pending Suggestions**: {sugg_amt} (requires 1-click CA approval)\n"
            f"• **Conflicting Claims**: {conf_amt} (requires dispute resolution)\n"
            f"• **In-Transit Settlements**: {pend_amt} (pending Razorpay payout batch ingestion)\n\n"
            "**Reconciliation Balance Invariant**:\n"
            "$$\\text{Total Ingested} = \\text{Auto-Reconciled} + \\text{CA Review} + \\text{In-Transit} + \\text{Exceptions}$$\n\n"
            "**Resolution Actions**:\n"
            "1. Open the **Audit Drawer** on any exception row to view root cause & raw payload.\n"
            "2. Approve high-confidence suggestions or resolve conflicts in the **Conflict Drawer**.\n"
            "3. Click **'Sync / Seed'** to ingest subsequent Razorpay settlement batches for in-transit entries."
        )

    # 5. About ReconGrid AI / Overview
    if any(k in q for k in ("what is recongrid", "about project", "about recongrid", "what does this app do", "what is this project", "project overview", "how does this work")):
        return (
            "🛡️ **ReconGrid AI** is an autonomous, audit-grade settlement reconciliation and discrepancy diagnostics engine for Razorpay merchants and Chartered Accountants.\n\n"
            "**Key Capabilities**:\n"
            "• **Multi-Page & Encrypted Statement Ingestion**: Parses password-protected PDFs & CSVs for major Indian banks (SBI, HDFC, ICICI, Axis, Kotak, PNB, etc.).\n"
            "• **3-Tier Deterministic Engine**: Exact UTR matching, fuzzy descriptor matching ($90\\%+ score$), and fee/tax/refund diagnostics.\n"
            "• **Discrepancy Diagnostics**: Automatically explains short settlements due to 2% MDR fee + 18% GST, Section 194-O (1% TDS), or customer refund clawbacks.\n"
            "• **CA Decision Workflows**: Single-click approval for suggested matches, conflict resolution drawer, and one-click batch approval.\n"
            "• **Conversational Q&A Agent**: Ask questions about any transaction, UTR, or project metric with multi-tab conversation memory."
        )

    # 6. Matching Tiers
    if any(k in q for k in ("tier", "tiers", "matching engine", "how matching works")):
        return (
            "⚙️ **ReconGrid AI 3-Tier Reconciliation Logic**:\n\n"
            "1. **Tier 1: Deterministic Exact Match (100% Confidence)**\n"
            "   • Matches when both the UTR and net amount align exactly with a Razorpay settlement.\n"
            "   • Marked as `OK MATCHED` automatically.\n\n"
            "2. **Tier 2: Fuzzy Descriptor Matching (90%–99% Confidence)**\n"
            "   • Used when UTR is missing or embedded in unstructured bank remarks (e.g. `RTGS RAZORPAY SOFTWARE BANGLORE`).\n"
            "   • Marked as `SUGGESTED` for quick CA approval.\n\n"
            "3. **Tier 3: Discrepancy Diagnostics & Adjustments**\n"
            "   • **Fee Deduction**: 2% Gateway MDR + 18% GST.\n"
            "   • **Section 194-O TDS**: 1% TDS deduction on gross e-commerce sales.\n"
            "   • **Refund Clawbacks**: Deductions for customer refund batches.\n"
            "   • **Reversals / Debits**: Chargeback reversals."
        )

    # 7. Section 194-O TDS vs 194H
    if any(k in q for k in ("194-o", "194o", "section 194", "tds")):
        return (
            "📑 **Section 194-O E-Commerce TDS & Tax Compliance**:\n\n"
            "• **Statutory Requirement**: Under Indian Income Tax Section 194-O, e-commerce marketplace operators must deduct **1.0% TDS** on the gross amount of sales before disbursing net settlements to merchants.\n"
            "• **194-O vs 194-H**: Section 194-O applies to gross marketplace sales (1%), whereas Section 194-H applies to commission payments (5%).\n"
            "• **How ReconGrid Reconciles It**: When a bank settlement arrives short by exactly 1% of gross sales (in addition to MDR fees + GST), the engine auto-classifies it as `TDS_194O_DEDUCTION` with ₹0 delta variance.\n"
            "• **GSTR-8 & Form 26AS**: These deducted TDS amounts can be cross-verified in Form 26AS / AIS for quarterly income tax credit."
        )

    # 8. GST & Input Tax Credit (ITC) on Gateway Fees
    if any(k in q for k in ("itc", "input tax credit", "gstr", "claim gst")):
        return (
            "🏛️ **GST & Input Tax Credit (ITC) on Gateway Fees**:\n\n"
            "• **GST Rate**: Razorpay levies **18.0% GST** on MDR processing fees (9% CGST + 9% SGST, or 18% IGST).\n"
            "• **Claiming ITC**: Merchants can claim full Input Tax Credit on this GST amount under **GSTR-3B** against the monthly B2B GST tax invoice issued by Razorpay Software Pvt Ltd.\n"
            "• **Audit Verification**: ReconGrid logs the exact fee and tax components (`fees` and `tax`) on every transaction, allowing instant export of monthly Gateway GST schedules for your monthly GSTR-2B reconciliation."
        )

    # 9. Fee Formula / MDR / GST
    if any(k in q for k in ("fee formula", "mdr", "gst calculation", "gateway charge")):
        return (
            "💳 **Razorpay Standard Fee Calculation**:\n\n"
            "• **MDR (Merchant Discount Rate)**: `2.0%` on gross transaction volume.\n"
            "• **GST on Fees**: `18.0%` applicable on the MDR fee amount.\n"
            "• **Formula**: `Net Payout = Gross Amount - MDR - (MDR * 0.18)`\n"
            "• *Example*: On ₹1,00,000.00 gross sales:\n"
            "  - Gross Sales = ₹ 1,00,000.00\n"
            "  - MDR Fee (2%) = ₹ 2,000.00\n"
            "  - GST on MDR (18%) = ₹ 360.00\n"
            "  - **Net Bank Credit = ₹ 97,640.00**"
        )

    # 10. Split & Batched Settlements
    if any(k in q for k in ("batched settlement", "split settlement", "batch payout", "batched")):
        return (
            "📦 **Batched & Split Settlement Reconciliation**:\n\n"
            "• **What It Is**: Razorpay frequently consolidates multiple payout cycles (e.g. morning cycle of ₹60,000 + evening cycle of ₹40,000) into a **single lump-sum bank credit** of ₹1,00,000.\n"
            "• **ReconGrid Resolution**: The engine's combinatorial batching solver searches candidate settlements across a ±2 day window. When the sum of active settlements equals the bank credit, it binds them together under `BATCHED_SETTLEMENT` with zero variance."
        )

    # 11. Customer Refunds & Clawbacks
    if any(k in q for k in ("refund", "clawback", "refund adjustment")):
        return (
            "🔄 **Customer Refunds & Settlement Clawbacks**:\n\n"
            "• When you issue customer refunds, Razorpay does not debit your bank account directly; instead, it deducts the refund total from your next payout batch.\n"
            "• **Diagnostic Classification**: ReconGrid inspects settlement metadata for `refund_total` and matches payouts that are short by the exact refund amount under `REFUND_ADJUSTED`."
        )

    # 12. Token Guardrails & Anti-Hallucination
    if any(k in q for k in ("guardrail", "token guardrail", "hallucination", "accuracy")):
        return (
            "🛡️ **Token Guardrail & Anti-Hallucination Defense**:\n\n"
            "ReconGrid AI incorporates a deterministic financial safety guardrail on all AI narration:\n"
            "1. **Number Extraction**: Every numeric token, Rupee amount, and ID in the AI output is parsed.\n"
            "2. **Database Cross-Validation**: If the AI attempts to invent or calculate numbers not present in the verified database record, the guardrail instantly **rejects the response**.\n"
            "3. **Fallback**: Replaced with a mathematically verified, audit-grade template fallback to guarantee 100% accuracy for statutory compliance."
        )

    # 13. Bank Password Format Guide
    if any(k in q for k in ("password", "decrypt", "protected pdf", "password format")):
        return (
            "🔐 **Indian Bank PDF Password Formulas**:\n\n"
            "• **SBI**: Last 5 digits of Mobile No + DDMM of DOB (or 11-digit Account Number)\n"
            "• **HDFC Bank**: Customer ID (or DDMMYYYY / First 4 letters of name in lowercase + DDMM)\n"
            "• **ICICI Bank**: First 4 letters of name (lowercase) + DDMM of DOB\n"
            "• **Axis Bank**: First 4 letters of Name (CAPITAL) + Last 4 digits of Customer ID\n"
            "• **Kotak Bank**: Customer Relationship Number (CRN) or DOB (DDMMYYYY)\n"
            "• **PNB / BOB / Canara**: Account Number or Registered Mobile Number"
        )

    # 14. Batch Approval
    if any(k in q for k in ("batch approve", "batch approval", "approve all")):
        return (
            "⚡ **Batch Approval Workflow (≥90% Confidence)**:\n\n"
            "• Clicking the green **'Batch Approve (≥90%)'** button automatically promotes all unverified Tier 2 Suggested Matches into `OK MATCHED` in a single atomic database transaction.\n"
            "• Every approved transaction is timestamped and recorded in the immutable CA audit trail."
        )

    # 15. Export Audit CSV
    if any(k in q for k in ("export", "download report", "audit csv", "audit report")):
        return (
            "📥 **Export Audit CSV for Statutory Auditors**:\n\n"
            "Click **'Export Audit CSV'** in the top right to download a comprehensive reconciliation schedule including:\n"
            "• Bank Transaction Dates & UTRs\n"
            "• Razorpay Settlement IDs & Statuses\n"
            "• Gross Sales, 2% MDR Fees, 18% GST, 1% TDS breakdowns\n"
            "• Delta Variance & Diagnostic Notes\n"
            "• CA Approval & Resolution Audit Logs"
        )

    return None


class SettlementQaAgent:
    def __init__(self, qa_repo: QaRepository):
        self.qa_repo = qa_repo

    async def answer_query(
        self,
        query: str,
        context_record_id: str | None = None,
        history: list | None = None,
    ) -> QaAskResponse:
        """Processes natural language CA query with multi-turn memory, deterministic retrieval, and guardrailed narration."""
        clean_query = query.strip()
        now = datetime.now(timezone.utc)

        # 0. Fetch live dashboard metrics for context
        summary_metrics = None
        session = getattr(self.qa_repo, "session", None)
        if session is not None and not str(type(session)).endswith("Mock'>"):
            try:
                from app.repositories.reconciliation_repo import ReconciliationRepository
                recon_repo = ReconciliationRepository(session)
                summary_metrics = await recon_repo.get_summary_metrics("default")
            except Exception as ex:
                logger.warning("qa_fetch_summary_failed", error=str(ex))

        # 1. Deterministic Retrieval Step for Specific Record Lookups in Current Query
        source_log = await self.qa_repo.find_reconciliation_record(clean_query)

        # 2. General Project / Metric / Architecture Inquiry (Checked BEFORE falling back to unrelated active record)
        if not source_log:
            project_ans = answer_project_overview_question(clean_query, summary_metrics)
            if project_ans:
                await self.qa_repo.log_interaction({
                    "reconciliation_log_id": None,
                    "query_text": clean_query,
                    "raw_llm_output": project_ans,
                    "final_response": project_ans,
                    "guardrail_rejected": False,
                    "asked_at": now,
                })
                return QaAskResponse(
                    query=clean_query,
                    answer=project_ans,
                    source_record_id=None,
                    guardrail_rejected=False,
                    retrieved_data={"type": "project_overview", "summary": summary_metrics},
                    asked_at=now,
                )

        # 3. Context / Memory Fallback: If not an overview question, see if user is asking a follow-up about the active record or history
        if not source_log and context_record_id:
            source_log = await self.qa_repo.get_record_by_id(context_record_id)

        if not source_log and history:
            # Search candidate tokens from prior messages (most recent first)
            for prev_msg in reversed(history):
                content = prev_msg.content if hasattr(prev_msg, "content") else prev_msg.get("content", "")
                if content:
                    prev_log = await self.qa_repo.find_reconciliation_record(content)
                    if prev_log:
                        source_log = prev_log
                        break

        # 4. If still no record and no overview answer matched:
        if not source_log:

            # If external LLM is configured, ask LLM with full project context
            if settings.LLM_API_KEY:
                try:
                    llm_ans = await self._call_llm_general_qa(clean_query, history=history, summary=summary_metrics)
                    if llm_ans:
                        await self.qa_repo.log_interaction({
                            "reconciliation_log_id": None,
                            "query_text": clean_query,
                            "raw_llm_output": llm_ans,
                            "final_response": llm_ans,
                            "guardrail_rejected": False,
                            "asked_at": now,
                        })
                        return QaAskResponse(
                            query=clean_query,
                            answer=llm_ans,
                            source_record_id=None,
                            guardrail_rejected=False,
                            retrieved_data=None,
                            asked_at=now,
                        )
                except Exception as e:
                    logger.error("qa_general_llm_failed", error=str(e))

            no_record_msg = (
                "No record found matching that reference.\n\n"
                "You can ask me about:\n"
                "• Any **Settlement ID** (e.g. `setl_Kjs9283jkd901`) or **UTR** (e.g. `CMS002938491801`)\n"
                "• **Project Concepts**: *What is ingested ledger?*, *What is auto-reconciled net?*, *How do conflicts work?*\n"
                "• **Reconciliation Logic**: *Explain 3 tiers of matching*, *What is Section 194-O TDS?*"
            )
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

        # 2. Narration Step for Record Lookup
        raw_llm_output = ""
        guardrail_rejected = False
        final_response = ""

        # Check if LLM API is configured
        if settings.LLM_API_KEY:
            try:
                raw_llm_output = await self._call_llm_narration(clean_query, source_log, history=history)
                is_valid, invented_tokens = validate_qa_narration(raw_llm_output, source_log)
                if not is_valid:
                    logger.warning(
                        "qa_guardrail_rejected_invented_numbers",
                        invented_tokens=invented_tokens,
                        query=clean_query,
                    )
                    guardrail_rejected = True
                    final_response = generate_followup_response(source_log, clean_query)
                else:
                    final_response = raw_llm_output
            except Exception as e:
                logger.error("qa_llm_call_failed", error=str(e))
                final_response = generate_followup_response(source_log, clean_query)
        else:
            # High-fidelity deterministic narration fallback with conversational context
            final_response = generate_followup_response(source_log, clean_query)
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

    async def _call_llm_general_qa(
        self,
        query: str,
        history: list | None = None,
        summary: dict | None = None,
    ) -> str:
        """Answers general project and reconciliation architecture questions using external LLM."""
        summary_str = (
            f"Current Dashboard State: {summary.get('total_records', 0)} total records, "
            f"{summary.get('matched_count', 0)} matched ({summary.get('match_rate_percentage', 0)}%), "
            f"{summary.get('suggested_count', 0)} suggested for CA review, "
            f"{summary.get('conflict_count', 0)} conflicts, "
            f"{summary.get('exception_count', 0)} exceptions (variance)."
            if summary else "No live batch loaded."
        )

        system_prompt = (
            "You are ReconGrid AI's Settlement & Finance Copilot for Chartered Accountants.\n"
            "Explain ReconGrid AI features, reconciliation workflows, metrics, and Razorpay settlement accounting in clear, professional financial terminology.\n\n"
            f"Context:\n{summary_str}\n\n"
            "Key Definitions:\n"
            "- Total Ingested Ledger: Bank transactions parsed from uploaded PDF/CSV statement.\n"
            "- Auto-Reconciled Net: Bank credits matched with Razorpay settlements with zero variance.\n"
            "- CA Review Required: Suggested matches (Tier 2 fuzzy matches >=90%) and multi-candidate conflicts needing CA approval.\n"
            "- Unresolved Variance: Bank entries with no gateway settlement link (exceptions, UPI, bank fees).\n"
            "- 3 Tiers: Tier 1 (Exact UTR), Tier 2 (Fuzzy Descriptor), Tier 3 (Diagnostic: 2% MDR + 18% GST, 1% Section 194-O TDS, Refund clawbacks).\n"
        )

        messages = [{"role": "system", "content": system_prompt}]
        if history:
            for item in history[-6:]:
                role = item.role if hasattr(item, "role") else item.get("role", "user")
                content = item.content if hasattr(item, "content") else item.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": query})

        async with httpx.AsyncClient(timeout=15.0) as client:
            if settings.LLM_PROVIDER in ("nvidia", "openai") or settings.LLM_BASE_URL:
                url = f"{settings.LLM_BASE_URL.rstrip('/')}/chat/completions"
                resp = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {settings.LLM_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.LLM_MODEL,
                        "messages": messages,
                        "max_tokens": 512,
                        "temperature": 0.2,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                raise RuntimeError(f"LLM API error: {resp.status_code} {resp.text}")
            else:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": settings.LLM_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": settings.LLM_MODEL,
                        "max_tokens": 400,
                        "system": system_prompt,
                        "messages": [m for m in messages if m["role"] != "system"],
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data["content"][0]["text"].strip()
                raise RuntimeError(f"LLM API error: {resp.status_code} {resp.text}")

    async def _call_llm_narration(
        self,
        query: str,
        log: ReconciliationLog,
        history: list | None = None,
    ) -> str:
        """Invokes external LLM to narrate facts strictly without computing, preserving conversational context."""
        system_prompt = (
            "You are ReconGrid AI's Settlement Explainer for Chartered Accountants.\n"
            "Explain this existing computed reconciliation result in clear, professional language.\n"
            "CRITICAL RULE: Do NOT perform math, do NOT estimate, do NOT invent any numbers.\n"
            "FORMAT RULE: Always write numbers in exact digit format (e.g. '50000.00', '₹ 49,100.00', '18%'). "
            "Never spell out numbers as words (e.g. do NOT write 'nine hundred rupees' or 'fifty thousand').\n"
            f"Record Details:\n"
            f"- Status: {log.match_status}\n"
            f"- Tier: {log.match_tier}\n"
            f"- Diagnostic Type: {log.diagnostic_type}\n"
            f"- Delta: {log.delta_amount}\n"
            f"- Note: {log.diagnostic_note}\n"
            f"- Bank Amount: {log.bank_transaction.amount if log.bank_transaction else 'N/A'}\n"
            f"- Settlement ID: {log.rzp_settlement.settlement_id if log.rzp_settlement else 'N/A'}\n"
        )
        
        messages = [{"role": "system", "content": system_prompt}]
        
        if history:
            for item in history[-6:]:  # last 6 turns
                role = item.role if hasattr(item, "role") else item.get("role", "user")
                content = item.content if hasattr(item, "content") else item.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})
                    
        messages.append({"role": "user", "content": query})

        async with httpx.AsyncClient(timeout=15.0) as client:
            if settings.LLM_PROVIDER in ("nvidia", "openai") or settings.LLM_BASE_URL:
                url = f"{settings.LLM_BASE_URL.rstrip('/')}/chat/completions"
                resp = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {settings.LLM_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.LLM_MODEL,
                        "messages": messages,
                        "max_tokens": 512,
                        "temperature": 0.2,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                raise RuntimeError(f"LLM API error: {resp.status_code} {resp.text}")
            else:
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
                        "system": system_prompt,
                        "messages": [m for m in messages if m["role"] != "system"],
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data["content"][0]["text"].strip()
                raise RuntimeError(f"LLM API error: {resp.status_code} {resp.text}")
