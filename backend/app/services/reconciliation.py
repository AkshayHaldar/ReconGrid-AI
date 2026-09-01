"""Deterministic Multi-Tier Reconciliation Engine.

No LLM involvement — pure deterministic rules and Decimal arithmetic.
"""

import re
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Sequence
from app.core.config import settings
from app.core.logging import logger
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.models.reconciliation_log import ReconciliationLog
from app.repositories.reconciliation_repo import ReconciliationRepository
from app.services.diagnostics import DiagnosticResult, DiagnosticsService
from app.utils.fuzzy import is_fuzzy_match
from app.utils.money import format_inr, is_amount_matching, to_decimal


def _normalize_utr(utr: str | None) -> str:
    """Strips delimiters and common banking transport/bank prefixes for resilient reference matching."""
    if not utr:
        return ""
    clean = re.sub(r"[\s\-_/]+", "", str(utr).strip().upper())
    prefixes = [
        "NEFT", "RTGS", "IMPS", "UPI", "CMS", "UTR", "CR", "DR",
        "HDFC", "ICIC", "SBIN", "AXIS", "KKBK", "PUNB", "BARB", "CNRB", "YESB"
    ]
    changed = True
    while changed:
        changed = False
        for pfx in prefixes:
            if clean.startswith(pfx) and len(clean) - len(pfx) >= 6:
                clean = clean[len(pfx):]
                changed = True
    return clean


def _to_utc_timestamp(dt: datetime | date | None) -> float:
    """Converts a datetime or date to UTC epoch timestamp."""
    if not dt:
        return 0.0
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return datetime.combine(dt, datetime.min.time(), tzinfo=timezone.utc).timestamp()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).timestamp()
    return dt.timestamp()


def _diff_seconds(dt1: datetime | date | None, dt2: datetime | date | None) -> float:
    """Safely calculates absolute difference in seconds between two datetimes/dates handling tz-awareness."""
    if not dt1 or not dt2:
        return float("inf")
    return abs(_to_utc_timestamp(dt1) - _to_utc_timestamp(dt2))


class _SettlementEntry:
    __slots__ = ("s", "settlement_id", "utr", "norm_utr", "ts", "amount", "gross", "norm_desc", "desc_tokens")

    def __init__(self, s: RazorpaySettlement):
        self.s = s
        self.settlement_id = s.settlement_id
        clean_utr = s.utr.strip().upper() if s.utr else ""
        self.utr = clean_utr
        self.norm_utr = _normalize_utr(clean_utr) if clean_utr else ""
        self.ts = _to_utc_timestamp(s.settlement_created_at)
        self.amount = to_decimal(s.amount)
        self.gross = to_decimal(s.gross_amount)
        raw_desc = s.raw_payload.get("description", "") or s.settlement_id or s.utr or ""
        from app.utils.fuzzy import normalize_descriptor
        self.norm_desc = normalize_descriptor(raw_desc)
        self.desc_tokens = set(self.norm_desc.split()) if self.norm_desc else set()


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

        # Precompute settlement cache entries
        settlement_entries = [_SettlementEntry(s) for s in settlements]

        # Map settlements by UTR, DB ID, and settlement_id for fast deterministic lookup
        settlements_by_utr: dict[str, list[RazorpaySettlement]] = {}
        settlements_by_norm_utr: dict[str, list[RazorpaySettlement]] = {}
        settlements_by_id: dict[str, RazorpaySettlement] = {}
        settlements_by_db_id: dict[str, RazorpaySettlement] = {}
        for entry in settlement_entries:
            s = entry.s
            settlements_by_id[entry.settlement_id] = s
            if s.id:
                settlements_by_db_id[s.id] = s
            if entry.utr:
                settlements_by_utr.setdefault(entry.utr, []).append(s)
                if entry.norm_utr:
                    settlements_by_norm_utr.setdefault(entry.norm_utr, []).append(s)

        precomputed_settlement_utrs = [
            (s_utr, _normalize_utr(s_utr), s_cands)
            for s_utr, s_cands in settlements_by_utr.items()
        ]

        # Retrieve prior active statuses for bank transactions in batch via fast status map
        prev_status_map = await self.recon_repo.get_active_status_map(batch_id=batch_id)

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
        now_ts = now.timestamp()
        pending_window_seconds = float(settings.SETTLEMENT_PENDING_WINDOW_DAYS * 86400)

        for bank_tx in sorted_bank_txs:
            bank_amount = to_decimal(bank_tx.amount)
            bank_utr = bank_tx.utr.strip().upper() if bank_tx.utr else None
            norm_bank_utr = _normalize_utr(bank_utr) if bank_utr else ""
            tx_ts = _to_utc_timestamp(bank_tx.date)
            candidate: RazorpaySettlement | None = None
            tier: str = "TIER_3"
            status: str = "EXCEPTION"
            diagnostic_type: str = "UNRESOLVED"
            confidence: float | None = None
            note: str = ""
            delta = Decimal("0.00")
            was_pending = prev_status_map.get(bank_tx.id) == "PENDING_SETTLEMENT_DATA"

            def _pick_best_candidate(candidate_list: list[RazorpaySettlement]) -> tuple[RazorpaySettlement, DiagnosticResult | None]:
                # 1. Exact net amount match
                for c in candidate_list:
                    if is_amount_matching(bank_amount, to_decimal(c.amount), tolerance):
                        return c, None
                # 2. Exact gross amount match
                for c in candidate_list:
                    if to_decimal(c.gross_amount) > Decimal("0.00") and is_amount_matching(bank_amount, to_decimal(c.gross_amount), tolerance):
                        return c, None
                # 3. Diagnostic match (Fee, TDS, Refund, Reversal, FX)
                for c in candidate_list:
                    diag = DiagnosticsService.evaluate_delta(bank_tx, c, tolerance)
                    if diag.match_status == "MATCHED":
                        return c, diag
                # 4. Default to first candidate
                first_c = candidate_list[0]
                return first_c, DiagnosticsService.evaluate_delta(bank_tx, first_c, tolerance)

            # --- TIER 1: Exact UTR Match ---
            candidates = None
            if bank_utr and bank_utr in settlements_by_utr:
                candidates = settlements_by_utr[bank_utr]
            elif norm_bank_utr and norm_bank_utr in settlements_by_norm_utr:
                candidates = settlements_by_norm_utr[norm_bank_utr]

            if candidates:
                candidate, diag_eval = _pick_best_candidate(candidates)
                if is_amount_matching(bank_amount, to_decimal(candidate.amount), tolerance):
                    tier = "TIER_1"
                    status = "MATCHED"
                    diagnostic_type = "EXACT_MATCH"
                    confidence = 1.00
                    note = f"Tier 1 exact match: UTR {bank_utr or norm_bank_utr} and amount {format_inr(bank_amount)}."
                else:
                    tier = "TIER_3"
                    diag = diag_eval or DiagnosticsService.evaluate_delta(bank_tx, candidate, tolerance)
                    status = diag.match_status
                    diagnostic_type = diag.diagnostic_type
                    delta = diag.delta_amount
                    note = f"Tier 3 diagnostic on UTR {bank_utr or norm_bank_utr}: {diag.diagnostic_note}"

            # --- TIER 1.5: Substring / Prefix-stripped UTR Match ---
            # Entropy Floor Rationale:
            # A 6-character alphanumeric token provides at least 36^6 (~2.17 billion) possible permutations,
            # ensuring sufficient entropy to prevent spurious random substring collisions in high-volume bank statements
            # while gracefully handling gateway truncation or transport prefix discrepancies (e.g. "CMS...", "NEFT-HDFC-...").
            # Safety Invariant:
            # Substring matches produce status="SUGGESTED" with confidence 0.98 (never a silent auto-MATCHED)
            # so that any false positive is always human-reviewable by a Chartered Accountant / Finance Controller.
            if not candidate and (bank_utr or norm_bank_utr):
                search_utrs = [u for u in [bank_utr, norm_bank_utr] if u and len(u) >= 6]
                if search_utrs:
                    for s_utr, s_norm, s_candidates in precomputed_settlement_utrs:
                        is_match = False
                        for su in search_utrs:
                            if (su in s_utr) or (s_utr in su) or (s_norm and su in s_norm) or (s_norm and s_norm in su):
                                is_match = True
                                break
                        if is_match:
                            candidate, diag_eval = _pick_best_candidate(s_candidates)
                            if is_amount_matching(bank_amount, to_decimal(candidate.amount), tolerance):
                                tier = "TIER_1"
                                status = "SUGGESTED"
                                diagnostic_type = "EXACT_MATCH"
                                confidence = 0.98
                                note = f"Tier 1.5 UTR reference substring match ({bank_utr} ~ {s_utr}) and amount {format_inr(bank_amount)}. Flagged as SUGGESTED for verification."
                            else:
                                tier = "TIER_3"
                                diag = diag_eval or DiagnosticsService.evaluate_delta(bank_tx, candidate, tolerance)
                                status = diag.match_status
                                diagnostic_type = diag.diagnostic_type
                                delta = diag.delta_amount
                                note = f"Tier 3 diagnostic on UTR ({bank_utr} ~ {s_utr}): {diag.diagnostic_note}"
                            break

            # --- TIER 2: Fuzzy Match on Descriptor Text ---
            if not candidate and bank_tx.description:
                from app.utils.fuzzy import normalize_descriptor
                tx_desc_norm = normalize_descriptor(bank_tx.description)
                tx_tokens = set(tx_desc_norm.split()) if tx_desc_norm else set()

                if tx_tokens:
                    best_match: RazorpaySettlement | None = None
                    best_score = 0.0

                    for entry in settlement_entries:
                        if entry.settlement_id in matched_settlement_ids:
                            continue
                        if abs(tx_ts - entry.ts) > 10 * 86400:
                            continue
                        if not (tx_tokens & entry.desc_tokens):
                            continue
                        matched, score = is_fuzzy_match(
                            bank_tx.description,
                            entry.norm_desc or entry.settlement_id,
                            threshold=fuzzy_threshold,
                        )
                        if matched and score > best_score:
                            best_score = score
                            best_match = entry.s

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

            # --- TIER 0: Fallback Match (Date Window ±3 days + Amount Fallback) ---
            if not candidate:
                date_window_sec = 3 * 86400  # ±3 days (72 hours)
                date_candidates = []
                for entry in settlement_entries:
                    if entry.settlement_id in matched_settlement_ids:
                        continue
                    time_diff = abs(tx_ts - entry.ts)
                    if time_diff <= date_window_sec:
                        s_amt = entry.amount
                        s_gross = entry.gross
                        if is_amount_matching(bank_amount, s_amt, tolerance) or (
                            s_gross > Decimal("0.00") and is_amount_matching(bank_amount, s_gross, tolerance)
                        ):
                            date_candidates.append((time_diff, entry.s))
                        elif bank_amount <= (s_gross if s_gross > Decimal("0.00") else s_amt) + tolerance:
                            diag = DiagnosticsService.evaluate_delta(bank_tx, entry.s, tolerance)
                            if diag.match_status == "MATCHED":
                                date_candidates.append((time_diff, entry.s))

                if date_candidates:
                    date_candidates.sort(key=lambda x: x[0])
                    candidate = date_candidates[0][1]
                    tier = "TIER_0"
                    status = "SUGGESTED"
                    diagnostic_type = "DATE_AMOUNT_FALLBACK"
                    confidence = 0.85
                    note = (
                        f"Tier 0 fallback match: date window ±3 days + amount {format_inr(bank_amount)} "
                        f"without UTR. Flagged as SUGGESTED for verification."
                    )

            # --- TIER 3b: Batched Settlements (Many-to-One Subset Sum) ---
            # Complexity budget: Candidates in ±4-day window bucketed and bounded to top 40 by time proximity.
            # Pairs (k=2): O(N log N) via two-pointer scan on amount-sorted array.
            # Triplets (k=3): O(N^2) bounded two-pointer scan on top 20 candidates.
            if not candidate and bank_amount > Decimal("0.00"):
                window_setls = [
                    entry.s for entry in settlement_entries
                    if entry.settlement_id not in matched_settlement_ids
                    and entry.amount < bank_amount
                    and abs(tx_ts - entry.ts) <= 4 * 86400
                ]
                window_setls.sort(key=lambda s: abs(tx_ts - _to_utc_timestamp(s.settlement_created_at)))
                window_candidates = window_setls[:40]

                # 1. Pairs (k=2): Two-pointer scan on amount-sorted candidates
                if len(window_candidates) >= 2:
                    sorted_pairs = sorted(window_candidates, key=lambda s: to_decimal(s.amount))
                    left = 0
                    right = len(sorted_pairs) - 1
                    while left < right:
                        s_left = sorted_pairs[left]
                        s_right = sorted_pairs[right]
                        combined = to_decimal(s_left.amount) + to_decimal(s_right.amount)
                        if is_amount_matching(bank_amount, combined, tolerance):
                            s1, s2 = s_left, s_right
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
                        elif combined < bank_amount - tolerance:
                            left += 1
                        else:
                            right -= 1

                # 2. Triplets (k=3): Bounded two-pointer scan with fixed first element on top 20 candidates
                if not candidate and len(window_candidates) >= 3:
                    triplet_pool = sorted(window_candidates[:20], key=lambda s: to_decimal(s.amount))
                    n_triplets = len(triplet_pool)
                    for i in range(n_triplets - 2):
                        s_i = triplet_pool[i]
                        amt_i = to_decimal(s_i.amount)
                        left = i + 1
                        right = n_triplets - 1
                        while left < right:
                            s_left = triplet_pool[left]
                            s_right = triplet_pool[right]
                            combined = amt_i + to_decimal(s_left.amount) + to_decimal(s_right.amount)
                            if is_amount_matching(bank_amount, combined, tolerance):
                                s1, s2, s3 = s_i, s_left, s_right
                                candidate = s1
                                tier = "TIER_3"
                                status = "MATCHED"
                                diagnostic_type = "BATCHED_SETTLEMENT"
                                confidence = 0.95
                                matched_settlement_ids.add(s1.settlement_id)
                                matched_settlement_ids.add(s2.settlement_id)
                                matched_settlement_ids.add(s3.settlement_id)
                                note = (
                                    f"Batched Settlement Match: Bank credit of {format_inr(bank_amount)} "
                                    f"matches 3 batched Razorpay payouts: {s1.settlement_id} ({format_inr(to_decimal(s1.amount))}) "
                                    f"+ {s2.settlement_id} ({format_inr(to_decimal(s2.amount))}) "
                                    f"+ {s3.settlement_id} ({format_inr(to_decimal(s3.amount))})."
                                )
                                break
                            elif combined < bank_amount - tolerance:
                                left += 1
                            else:
                                right -= 1
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
                # Find matching settlement via O(1) dictionary lookup
                target_setl = settlements_by_db_id.get(settlement_db_id)
                if target_setl and len(settlement_match_counts.get(target_setl.settlement_id, [])) > 1:
                    item["match_status"] = "CONFLICT"
                    item["confidence_score"] = 0.50
                    item["diagnostic_note"] = (
                        f"Conflict: Settlement {target_setl.settlement_id} matches multiple bank rows. "
                        f"Locked until human merges or resolves."
                    )

        # Bulk supersede and persist immutable logs to database
        bank_tx_ids = [r["bank_tx_id"] for r in results]
        await self.recon_repo.supersede_batch_logs(bank_tx_ids)
        saved_logs = await self.recon_repo.add_logs_bulk(results)

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
