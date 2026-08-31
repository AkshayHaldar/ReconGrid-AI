"""Deterministic Multi-Tier Reconciliation Engine.

No LLM involvement — pure deterministic rules and Decimal arithmetic.
"""

import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Sequence
from app.core.config import settings
from app.core.logging import logger
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.models.reconciliation_log import ReconciliationLog
from app.repositories.reconciliation_repo import ReconciliationRepository
from app.services.diagnostics import DiagnosticsService
from app.utils.fuzzy import is_fuzzy_match
from app.utils.money import format_inr, is_amount_matching, to_decimal


def _diff_seconds(dt1: datetime | None, dt2: datetime | None) -> float:
    """Safely calculates absolute difference in seconds between two datetimes handling tz-awareness."""
    if not dt1 or not dt2:
        return float("inf")
    if dt1.tzinfo is None:
        dt1 = dt1.replace(tzinfo=timezone.utc)
    if dt2.tzinfo is None:
        dt2 = dt2.replace(tzinfo=timezone.utc)
    return abs((dt1 - dt2).total_seconds())


class ReconciliationEngine:
    def __init__(self, recon_repo: ReconciliationRepository):
        self.recon_repo = recon_repo

    async def reconcile_batch(
        self,
        bank_transactions: Sequence[BankTransaction],
        settlements: Sequence[RazorpaySettlement],
        batch_id: str = "default",
    ) -> list[ReconciliationLog]:
        """Runs the deterministic multi-tier matching pipeline across the dataset."""
        t_start = time.perf_counter()
        tolerance = settings.RECONCILIATION_TOLERANCE_INR
        fuzzy_threshold = settings.FUZZY_MATCH_CONFIDENCE_THRESHOLD

        # Map settlements by UTR and ID for fast deterministic lookup
        settlements_by_utr: dict[str, list[RazorpaySettlement]] = {}
        settlements_by_id: dict[str, RazorpaySettlement] = {}
        for s in settlements:
            settlements_by_id[s.settlement_id] = s
            if s.utr:
                clean_utr = s.utr.strip().upper()
                settlements_by_utr.setdefault(clean_utr, []).append(s)

        # Retrieve prior active statuses for bank transactions in batch to track state transitions
        active_logs, _ = await self.recon_repo.get_active_logs(
            batch_id=batch_id,
            page_size=max(len(bank_transactions) * 2, 500),
        )
        prev_status_map = {l.bank_tx_id: l.match_status for l in active_logs}

        # Prioritize previously pending transactions so they match newly arrived settlements first
        sorted_bank_txs = sorted(
            bank_transactions,
            key=lambda tx: 0 if prev_status_map.get(tx.id) == "PENDING_SETTLEMENT_DATA" else 1,
        )

        # Track settlement candidate matches to detect multi-bank row conflicts
        settlement_match_counts: dict[str, list[str]] = {}  # settlement_id -> [bank_tx_id, ...]
        results: list[dict] = []
        matched_settlement_ids: set[str] = set()

        now = datetime.now(timezone.utc)
        pending_window_seconds = float(settings.SETTLEMENT_PENDING_WINDOW_DAYS * 86400)

        for bank_tx in sorted_bank_txs:
            bank_amount = to_decimal(bank_tx.amount)
            bank_utr = bank_tx.utr.strip().upper() if bank_tx.utr else None
            candidate: RazorpaySettlement | None = None
            tier: str = "TIER_3"
            status: str = "EXCEPTION"
            diagnostic_type: str = "UNRESOLVED"
            confidence: float | None = None
            note: str = ""
            delta = Decimal("0.00")
            was_pending = prev_status_map.get(bank_tx.id) == "PENDING_SETTLEMENT_DATA"

            # --- TIER 1: Exact UTR Match ---
            if bank_utr and bank_utr in settlements_by_utr:
                candidates = settlements_by_utr[bank_utr]
                # Pick best candidate matching amount or first candidate
                exact_amt_candidate = next(
                    (c for c in candidates if is_amount_matching(bank_amount, to_decimal(c.amount), tolerance)),
                    None,
                )
                candidate = exact_amt_candidate or candidates[0]

                if candidate:
                    if is_amount_matching(bank_amount, to_decimal(candidate.amount), tolerance):
                        tier = "TIER_1"
                        status = "MATCHED"
                        diagnostic_type = "EXACT_MATCH"
                        confidence = 1.00
                        note = f"Tier 1 exact match: UTR {bank_utr} and amount {format_inr(bank_amount)}."
                    else:
                        # UTR matches but amount differs -> Tier 3 Diagnostics
                        tier = "TIER_3"
                        diag = DiagnosticsService.evaluate_delta(bank_tx, candidate, tolerance)
                        status = diag.match_status
                        diagnostic_type = diag.diagnostic_type
                        delta = diag.delta_amount
                        note = f"Tier 3 diagnostic on UTR {bank_utr}: {diag.diagnostic_note}"

            # --- TIER 1.5: Substring / Prefix-stripped UTR Match ---
            if not candidate and bank_utr:
                for s_utr, candidates in settlements_by_utr.items():
                    if len(bank_utr) >= 6 and len(s_utr) >= 6:
                        if bank_utr in s_utr or s_utr in bank_utr:
                            exact_amt_candidate = next(
                                (c for c in candidates if is_amount_matching(bank_amount, to_decimal(c.amount), tolerance)),
                                None,
                            )
                            candidate = exact_amt_candidate or candidates[0]
                            if candidate:
                                if is_amount_matching(bank_amount, to_decimal(candidate.amount), tolerance):
                                    tier = "TIER_1"
                                    status = "MATCHED"
                                    diagnostic_type = "EXACT_MATCH"
                                    confidence = 0.98
                                    note = f"Tier 1 UTR reference match ({bank_utr} ~ {s_utr}) and amount {format_inr(bank_amount)}."
                                else:
                                    tier = "TIER_3"
                                    diag = DiagnosticsService.evaluate_delta(bank_tx, candidate, tolerance)
                                    status = diag.match_status
                                    diagnostic_type = diag.diagnostic_type
                                    delta = diag.delta_amount
                                    note = f"Tier 3 diagnostic on UTR ({bank_utr} ~ {s_utr}): {diag.diagnostic_note}"
                                break

            # --- TIER 2: Fuzzy Match on Descriptor Text ---
            if not candidate:
                best_match: RazorpaySettlement | None = None
                best_score = 0.0

                for s in settlements:
                    if s.settlement_id in matched_settlement_ids:
                        continue
                    matched, score = is_fuzzy_match(
                        bank_tx.description,
                        s.raw_payload.get("description", "") or s.settlement_id or s.utr,
                        threshold=fuzzy_threshold,
                    )
                    if matched and score > best_score:
                        best_score = score
                        best_match = s

                if best_match:
                    candidate = best_match
                    confidence = best_score
                    tier = "TIER_2"
                    status = "SUGGESTED"
                    diagnostic_type = "FUZZY_MATCH"
                    delta = abs(bank_amount - to_decimal(candidate.amount))
                    note = (
                        f"Tier 2 fuzzy descriptor similarity ({round(best_score * 100, 1)}%) "
                        f"with settlement {candidate.settlement_id}. Requires CA approval."
                    )

            # --- TIER 0: Fallback Match (Date Window ±2 days + Exact Amount) ---
            if not candidate:
                date_candidates = []
                for s in settlements:
                    if s.settlement_id in matched_settlement_ids:
                        continue
                    # Check date window
                    time_diff = _diff_seconds(bank_tx.date, s.settlement_created_at)
                    if time_diff <= 2 * 86400:  # ±2 days window
                        if is_amount_matching(bank_amount, to_decimal(s.amount), tolerance):
                            date_candidates.append(s)

                if date_candidates:
                    candidate = date_candidates[0]
                    tier = "TIER_0"
                    status = "SUGGESTED"
                    diagnostic_type = "DATE_AMOUNT_FALLBACK"
                    confidence = 0.85
                    note = (
                        f"Tier 0 fallback match: date window ±2 days + exact amount {format_inr(bank_amount)} "
                        f"without UTR. Flagged as SUGGESTED for verification."
                    )

            # --- TIER 3b: Batched Settlements (Many-to-One Subset Sum) ---
            if not candidate and bank_amount > Decimal("0.00"):
                # Look for pairs of unallocated settlements in same date window whose sum equals bank_amount
                # Capped to 50 closest candidates to bound O(n²) pair comparisons at 1,225 per row
                window_setls = sorted(
                    [
                        s for s in settlements
                        if s.settlement_id not in matched_settlement_ids
                        and _diff_seconds(bank_tx.date, s.settlement_created_at) <= 3 * 86400
                    ],
                    key=lambda s: _diff_seconds(bank_tx.date, s.settlement_created_at),
                )[:50]
                for i in range(len(window_setls)):
                    for j in range(i + 1, len(window_setls)):
                        s1, s2 = window_setls[i], window_setls[j]
                        combined = to_decimal(s1.amount) + to_decimal(s2.amount)
                        if is_amount_matching(bank_amount, combined, tolerance):
                            candidate = s1
                            tier = "TIER_3"
                            status = "MATCHED"
                            diagnostic_type = "BATCHED_SETTLEMENT"
                            confidence = 0.95
                            matched_settlement_ids.add(s1.settlement_id)
                            matched_settlement_ids.add(s2.settlement_id)
                            note = (
                                f"Batched Settlement Match: Bank credit of {format_inr(bank_amount)} "
                                f"matches 2 batched Razorpay payouts: {s1.settlement_id} ({format_inr(to_decimal(s1.amount))}) "
                                f"+ {s2.settlement_id} ({format_inr(to_decimal(s2.amount))})."
                            )
                            break
                    if candidate:
                        break

            # Annotate auto-resolution transition if row was previously pending
            if candidate and was_pending:
                note = f"Auto-resolved from PENDING_SETTLEMENT_DATA on settlement sync: {note}"

            # --- UNMATCHED ROW: PENDING_SETTLEMENT_DATA vs EXCEPTION ---
            if not candidate:
                tx_dt = bank_tx.date
                if isinstance(tx_dt, datetime):
                    tx_aware = tx_dt if tx_dt.tzinfo else tx_dt.replace(tzinfo=timezone.utc)
                    age_seconds = (now - tx_aware).total_seconds()
                elif hasattr(tx_dt, "year"):
                    age_seconds = float((now.date() - tx_dt).days * 86400)
                else:
                    age_seconds = float("inf")

                delta = bank_amount
                if age_seconds <= pending_window_seconds:
                    tier = "TIER_3"
                    status = "PENDING_SETTLEMENT_DATA"
                    diagnostic_type = "PENDING_SETTLEMENT"
                    note = (
                        f"Awaiting settlement data from Razorpay (within {settings.SETTLEMENT_PENDING_WINDOW_DAYS}-day "
                        f"settlement window). Will auto-reconcile upon next sync."
                    )
                else:
                    tier = "TIER_3"
                    status = "EXCEPTION"
                    diagnostic_type = "UNRESOLVED"
                    if was_pending:
                        note = (
                            f"No matching Razorpay settlement found after pending window expired "
                            f"({format_inr(bank_amount)}, ref: {bank_utr or 'N/A'})."
                        )
                    else:
                        note = (
                            f"No matching Razorpay settlement found for bank row "
                            f"({format_inr(bank_amount)}, ref: {bank_utr or 'N/A'})."
                        )

            if candidate:
                settlement_match_counts.setdefault(candidate.settlement_id, []).append(bank_tx.id)
                if status == "MATCHED":
                    matched_settlement_ids.add(candidate.settlement_id)

            results.append({
                "batch_id": batch_id,
                "bank_tx_id": bank_tx.id,
                "rzp_settlement_id": candidate.id if candidate else None,
                "match_status": status,
                "match_tier": tier,
                "confidence_score": confidence,
                "delta_amount": delta,
                "diagnostic_type": diagnostic_type,
                "diagnostic_note": note,
                "matched_at": datetime.now(timezone.utc),
                "superseded": False,
            })

        # --- CONFLICT RESOLUTION PASS ---
        # If any settlement ID was matched to > 1 bank transaction, flag both as CONFLICT
        for item in results:
            settlement_db_id = item["rzp_settlement_id"]
            if settlement_db_id:
                # Find matching settlement_id
                target_setl = next((s for s in settlements if s.id == settlement_db_id), None)
                if target_setl and len(settlement_match_counts.get(target_setl.settlement_id, [])) > 1:
                    item["match_status"] = "CONFLICT"
                    item["confidence_score"] = 0.50
                    item["diagnostic_note"] = (
                        f"Conflict: Settlement {target_setl.settlement_id} matches multiple bank rows. "
                        f"Locked until human merges or resolves."
                    )

        # Write immutable logs to database
        saved_logs: list[ReconciliationLog] = []
        for r in results:
            await self.recon_repo.supersede_previous_logs(r["bank_tx_id"])
            log = await self.recon_repo.add_log(r)
            saved_logs.append(log)

        t_elapsed = max(time.perf_counter() - t_start, 0.0001)
        measured_rps = len(saved_logs) / t_elapsed

        logger.info(
            "reconciliation_batch_completed",
            batch_id=batch_id,
            total=len(saved_logs),
            matched=sum(1 for l in saved_logs if l.match_status == "MATCHED"),
            suggested=sum(1 for l in saved_logs if l.match_status == "SUGGESTED"),
            conflicts=sum(1 for l in saved_logs if l.match_status == "CONFLICT"),
            exceptions=sum(1 for l in saved_logs if l.match_status == "EXCEPTION"),
            pending=sum(1 for l in saved_logs if l.match_status == "PENDING_SETTLEMENT_DATA"),
            elapsed_seconds=round(t_elapsed, 4),
            rows_per_second=round(measured_rps, 1),
        )
        return saved_logs
