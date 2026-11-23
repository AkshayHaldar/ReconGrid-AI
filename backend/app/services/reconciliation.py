"""Deterministic Multi-Tier Reconciliation Engine.

No LLM involvement — pure deterministic rules and Decimal arithmetic.
"""

import hashlib
import hmac
import json
import re
import time
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from app.core.config import settings
from app.core.logging import logger
from app.core.telemetry import (
    recon_batch_duration_seconds,
    recon_exceptions_total,
    recon_matches_total,
    recon_total_rows_processed,
    tracer,
)
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.models.reconciliation_log import AUDITED_FIELDS, ReconciliationLog, compute_entry_hash, compute_link_hash
from app.repositories.reconciliation_repo import ReconciliationRepository
from app.repositories.settlement_repo import SettlementRepository
from app.services.batch_lock import ensure_batch_unlocked
from app.services.diagnostics import DiagnosticResult, DiagnosticsService
from app.utils.fuzzy import is_fuzzy_match
from app.utils.money import format_inr, is_amount_matching, to_decimal


def _normalize_utr(utr: str | None) -> str:
    """Strips delimiters and common banking transport/bank prefixes for resilient reference matching."""
    if not utr:
        return ""
    clean = re.sub(r"[\s\-_/]+", "", str(utr).strip().upper())
    prefixes = [
        "NEFT",
        "RTGS",
        "IMPS",
        "UPI",
        "CMS",
        "UTR",
        "CR",
        "DR",
        "HDFC",
        "ICIC",
        "SBIN",
        "AXIS",
        "KKBK",
        "PUNB",
        "BARB",
        "CNRB",
        "YESB",
    ]
    changed = True
    while changed:
        changed = False
        for pfx in prefixes:
            if clean.startswith(pfx) and len(clean) - len(pfx) >= 6:
                clean = clean[len(pfx) :]
                changed = True
    return clean


def _to_utc_timestamp(dt: datetime | date | None) -> float:
    """Converts a datetime or date to UTC epoch timestamp."""
    if not dt:
        return 0.0
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return datetime.combine(dt, datetime.min.time(), tzinfo=UTC).timestamp()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC).timestamp()
    return dt.timestamp()


def _diff_seconds(dt1: datetime | date | None, dt2: datetime | date | None) -> float:
    """Safely calculates absolute difference in seconds between two datetimes/dates handling tz-awareness."""
    if not dt1 or not dt2:
        return float("inf")
    return abs(_to_utc_timestamp(dt1) - _to_utc_timestamp(dt2))


class _SettlementEntry:
    __slots__ = ("amount", "desc_tokens", "gross", "norm_desc", "norm_utr", "s", "settlement_id", "ts", "utr")

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
        self.settlement_repo = SettlementRepository(recon_repo.session)

    async def reconcile_batch(
        self,
        bank_transactions: Sequence[BankTransaction],
        settlements: Sequence[RazorpaySettlement],
        batch_id: str = "default",
        *,
        incremental: bool = False,
    ) -> list[ReconciliationLog]:
        """Runs the deterministic multi-tier matching pipeline across the dataset.

        Raises BatchLockedError (HTTP 423) if the batch was signed off: a closed period is never re-matched.
        """
        await ensure_batch_unlocked(self.recon_repo, batch_id)
        with recon_batch_duration_seconds.time():
            t_start = time.perf_counter()
            tolerance = settings.RECONCILIATION_TOLERANCE_INR
            fuzzy_threshold = settings.FUZZY_MATCH_CONFIDENCE_THRESHOLD
            refund_totals = await self.settlement_repo.get_processed_refund_totals(
                {settlement.settlement_id for settlement in settlements}
            )

            def evaluate(bank_tx: BankTransaction, settlement: RazorpaySettlement) -> DiagnosticResult:
                return DiagnosticsService.evaluate_delta(
                    bank_tx, settlement, tolerance,
                    persisted_refund_total=refund_totals.get(settlement.settlement_id, Decimal("0.00")),
                )

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
                (s_utr, _normalize_utr(s_utr), s_cands) for s_utr, s_cands in settlements_by_utr.items()
            ]

            # Retrieve prior active statuses for bank transactions in batch via fast status map
            prev_status_map = await self.recon_repo.get_active_status_map(batch_id=batch_id)

            prior_claims: dict[str, list[ReconciliationLog]] = {}
            matched_settlement_ids: set[str] = set()
            if incremental:
                # Reuploads retain resolved decisions and retry only pending or unlogged rows.
                bank_transactions = [
                    tx for tx in bank_transactions if prev_status_map.get(tx.id) in (None, "PENDING_SETTLEMENT_DATA")
                ]
                for claim in await self.recon_repo.get_active_claims(batch_id):
                    settlement = settlements_by_db_id.get(claim.rzp_settlement_id or "")
                    if settlement is None:
                        continue
                    prior_claims.setdefault(settlement.settlement_id, []).append(claim)
                    if claim.match_status in ("MATCHED", "CONFLICT"):
                        matched_settlement_ids.add(settlement.settlement_id)

            recon_total_rows_processed.inc(len(bank_transactions))
            # Prioritize previously pending transactions so they match newly arrived settlements first.
            sorted_bank_txs = sorted(
                bank_transactions,
                key=lambda tx: 0 if prev_status_map.get(tx.id) == "PENDING_SETTLEMENT_DATA" else 1,
            )

            settlement_match_counts: dict[str, list[str]] = {}
            results: list[dict] = []
            item_tier_metrics: list[str | None] = []

            now = datetime.now(UTC)
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
                matched_tier_metric: str | None = None
                was_pending = prev_status_map.get(bank_tx.id) == "PENDING_SETTLEMENT_DATA"

                def _pick_best_candidate(
                    candidate_list: list[RazorpaySettlement],
                ) -> tuple[RazorpaySettlement, DiagnosticResult | None]:
                    # 1. Exact net amount match
                    for c in candidate_list:
                        if is_amount_matching(bank_amount, to_decimal(c.amount), tolerance):
                            return c, None
                    # 2. Exact gross amount match
                    for c in candidate_list:
                        if to_decimal(c.gross_amount) > Decimal("0.00") and is_amount_matching(
                            bank_amount, to_decimal(c.gross_amount), tolerance
                        ):
                            return c, None
                    # 3. Diagnostic match (Fee, TDS, Refund, Reversal, FX)
                    for c in candidate_list:
                        diag = evaluate(bank_tx, c)
                        if diag.match_status == "MATCHED":
                            return c, diag
                    # 4. Default to first candidate
                    first_c = candidate_list[0]
                    return first_c, evaluate(bank_tx, first_c)

                # --- TIER 1: Exact UTR Match ---
                with tracer.start_as_current_span("recon.tier1_exact_match"):
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
                            matched_tier_metric = "tier1"
                            note = f"Tier 1 exact match: UTR {bank_utr or norm_bank_utr} and amount {format_inr(bank_amount)}."
                        else:
                            tier = "TIER_3"
                            diag = diag_eval or evaluate(bank_tx, candidate)
                            status = diag.match_status
                            diagnostic_type = diag.diagnostic_type
                            delta = diag.delta_amount
                            if status == "MATCHED":
                                matched_tier_metric = "tier3"
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
                                if (
                                    (su in s_utr)
                                    or (s_utr in su)
                                    or (s_norm and su in s_norm)
                                    or (s_norm and s_norm in su)
                                ):
                                    is_match = True
                                    break
                            if is_match:
                                candidate, diag_eval = _pick_best_candidate(s_candidates)
                                if is_amount_matching(bank_amount, to_decimal(candidate.amount), tolerance):
                                    tier = "TIER_1"
                                    status = "SUGGESTED"
                                    diagnostic_type = "EXACT_MATCH"
                                    confidence = 0.98
                                    matched_tier_metric = "tier1_5"
                                    note = f"Tier 1.5 UTR reference substring match ({bank_utr} ~ {s_utr}) and amount {format_inr(bank_amount)}. Flagged as SUGGESTED for verification."
                                else:
                                    tier = "TIER_3"
                                    diag = diag_eval or evaluate(bank_tx, candidate)
                                    status = diag.match_status
                                    diagnostic_type = diag.diagnostic_type
                                    delta = diag.delta_amount
                                    if status == "MATCHED":
                                        matched_tier_metric = "tier3"
                                    note = f"Tier 3 diagnostic on UTR ({bank_utr} ~ {s_utr}): {diag.diagnostic_note}"
                                break

                # --- TIER 2: Fuzzy Match on Descriptor Text ---
                if not candidate and bank_tx.description:
                    with tracer.start_as_current_span("recon.tier2_fuzzy_similarity"):
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
                                matched_tier_metric = "tier2"
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
                                diag = evaluate(bank_tx, entry.s)
                                if diag.match_status == "MATCHED":
                                    date_candidates.append((time_diff, entry.s))

                    if date_candidates:
                        date_candidates.sort(key=lambda x: x[0])
                        candidate = date_candidates[0][1]
                        tier = "TIER_0"
                        status = "SUGGESTED"
                        diagnostic_type = "DATE_AMOUNT_FALLBACK"
                        confidence = 0.85
                        matched_tier_metric = "tier0"
                        note = (
                            f"Tier 0 fallback match: date window ±3 days + amount {format_inr(bank_amount)} "
                            f"without UTR. Flagged as SUGGESTED for verification."
                        )

                # --- TIER 3b: Batched Settlements (Many-to-One Subset Sum) ---
                # Complexity budget: Candidates in ±4-day window bucketed and bounded to top 40 by time proximity.
                # Pairs (k=2): O(N log N) via two-pointer scan on amount-sorted array.
                # Triplets (k=3): O(N^2) bounded two-pointer scan on top 20 candidates.
                if not candidate and bank_amount > Decimal("0.00"):
                    with tracer.start_as_current_span("recon.tier3b_subset_sum"):
                        window_setls = [
                            entry.s
                            for entry in settlement_entries
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
                                    matched_tier_metric = "tier3b"
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
                                        matched_tier_metric = "tier3b"
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
                        tx_aware = tx_dt if tx_dt.tzinfo else tx_dt.replace(tzinfo=UTC)
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

                if incremental and was_pending and status == "PENDING_SETTLEMENT_DATA":
                    continue

                if candidate:
                    settlement_match_counts.setdefault(candidate.settlement_id, []).append(bank_tx.id)
                    if status == "MATCHED":
                        matched_settlement_ids.add(candidate.settlement_id)

                item_tier_metrics.append(matched_tier_metric)
                results.append(
                    {
                        "batch_id": batch_id,
                        "bank_tx_id": bank_tx.id,
                        "rzp_settlement_id": candidate.id if candidate else None,
                        "match_status": status,
                        "match_tier": tier,
                        "confidence_score": confidence,
                        "delta_amount": delta,
                        "diagnostic_type": diagnostic_type,
                        "diagnostic_note": note,
                        "matched_at": datetime.now(UTC),
                        "superseded": False,
                    }
                )

            # Only newly contested settlements need a new decision.
            conflict_notes = {
                settlement_id: (
                    f"Conflict: Settlement {settlement_id} matches multiple bank rows. "
                    "Locked until human merges or resolves."
                )
                for settlement_id, bank_ids in settlement_match_counts.items()
                if len(bank_ids) + len(prior_claims.get(settlement_id, ())) > 1
            }
            for item in results:
                settlement = settlements_by_db_id.get(item["rzp_settlement_id"])
                if settlement and settlement.settlement_id in conflict_notes:
                    item.update(
                        match_status="CONFLICT",
                        confidence_score=0.50,
                        diagnostic_note=conflict_notes[settlement.settlement_id],
                    )

            for settlement_id, note in conflict_notes.items():
                for claim in prior_claims.get(settlement_id, ()):
                    if claim.match_status == "CONFLICT" or claim.human_action is not None:
                        continue
                    results.append(
                        {
                            "batch_id": batch_id,
                            "bank_tx_id": claim.bank_tx_id,
                            "rzp_settlement_id": claim.rzp_settlement_id,
                            "match_status": "CONFLICT",
                            "match_tier": claim.match_tier,
                            "confidence_score": 0.50,
                            "delta_amount": claim.delta_amount,
                            "diagnostic_type": claim.diagnostic_type,
                            "diagnostic_note": note,
                            "matched_at": now,
                            "superseded": False,
                        }
                    )

            # Bulk supersede and persist immutable logs to database.
            # Each new log is sealed onto the batch's SHA-256 audit chain in the ReconciliationLog before_flush hook.
            with tracer.start_as_current_span("recon.db_bulk_upsert"):
                bank_tx_ids = [r["bank_tx_id"] for r in results]
                await self.recon_repo.supersede_batch_logs(bank_tx_ids, batch_id=batch_id)
                saved_logs = await self.recon_repo.add_logs_bulk(results)

            # Increment Prometheus metrics for tier matches and exceptions
            for item, tier_metric in zip(results, item_tier_metrics):
                if item["match_status"] in ("MATCHED", "SUGGESTED"):
                    if tier_metric:
                        recon_matches_total.labels(tier=tier_metric).inc()
                elif item["match_status"] == "EXCEPTION":
                    recon_exceptions_total.inc()

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


@dataclass
class AuditChainResult:
    """Outcome of walking a batch's SHA-256 audit chain from the first row."""

    status: str  # VERIFIED | COMPROMISED
    tampered: bool
    total_records: int
    verified_records: int
    chain_head: str | None = None
    failed_at_id: str | None = None
    expected_hash: str | None = None
    actual_hash: str | None = None
    reason: str | None = None


class _ChainWalker:
    """Takes log rows in chain order, one at a time, and remembers the first one that is broken.

    Works on ORM logs or plain rows: it only reads the audited columns, previous_hash and entry_hash.
    """

    def __init__(self) -> None:
        self.expected_previous: str | None = None
        self.total = 0
        self.verified = 0
        self.failure: AuditChainResult | None = None

    def feed(self, log: Any) -> None:
        self.total += 1
        if self.failure is not None:
            return  # already compromised: only keep counting so total_records stays the batch size
        values = {name: getattr(log, name) for name in AUDITED_FIELDS}
        if log.previous_hash != self.expected_previous:
            # A row was deleted, inserted or reordered (or its predecessor's identity was edited).
            self.failure = self._broken(log, "BROKEN_CHAIN_LINK", self.expected_previous, log.previous_hash)
            return
        recomputed = compute_entry_hash(values, log.previous_hash)
        if recomputed != log.entry_hash:
            self.failure = self._broken(log, "ENTRY_HASH_MISMATCH", recomputed, log.entry_hash)
            return
        self.expected_previous = compute_link_hash(values, log.previous_hash)
        self.verified += 1

    def _broken(self, log: Any, reason: str, expected: str | None, actual: str | None) -> AuditChainResult:
        return AuditChainResult(
            status="COMPROMISED",
            tampered=True,
            total_records=0,  # filled in by result() once every row has been counted
            verified_records=self.verified,
            failed_at_id=log.id,
            expected_hash=expected,
            actual_hash=actual,
            reason=reason,
        )

    def result(self) -> AuditChainResult:
        if self.failure is not None:
            return replace(self.failure, total_records=self.total)
        return AuditChainResult(
            status="VERIFIED",
            tampered=False,
            total_records=self.total,
            verified_records=self.verified,
            chain_head=self.expected_previous,
        )


def verify_chain(logs: Iterable[Any]) -> AuditChainResult:
    """Checks, in chain order, that every row links to its predecessor and still matches its own entry_hash.

    O(N): each row is hashed once. Reports the first broken row so the caller gets its exact id.
    """
    walker = _ChainWalker()
    for log in logs:
        walker.feed(log)
    return walker.result()


async def verify_batch_audit_chain(recon_repo: ReconciliationRepository, batch_id: str) -> AuditChainResult:
    """Verifies the whole SHA-256 audit chain of a batch against what is actually stored in the database.

    Rows are streamed from the database in chunks, so memory stays flat however many logs the batch holds.
    """
    walker = _ChainWalker()
    async for row in recon_repo.stream_chain_rows(batch_id):
        walker.feed(row)
    return walker.result()


def build_audit_certificate(batch_id: str, result: AuditChainResult, signing_key: str = "") -> dict:
    """Audit Compliance Certificate: the verification result plus a content hash and, when a key is set, an HMAC."""
    body = {
        "certificate_type": "RECONGRID_AUDIT_COMPLIANCE_CERTIFICATE",
        "version": 1,
        "batch_id": batch_id,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "hash_algorithm": "SHA-256",
        "verification": asdict(result),
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    signed = bool(signing_key)
    return {
        **body,
        "content_sha256": hashlib.sha256(canonical).hexdigest(),
        "signed": signed,
        "signature_algorithm": "HMAC-SHA256" if signed else None,
        "signature": hmac.new(signing_key.encode(), canonical, hashlib.sha256).hexdigest() if signed else None,
    }
