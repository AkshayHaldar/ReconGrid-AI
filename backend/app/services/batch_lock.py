"""Month-end close: pre-flight checks, sign-off and the write guard for locked batches."""

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.reconciliation_log import ReconciliationBatch
from app.repositories.reconciliation_repo import ReconciliationRepository
from app.schemas.reconciliation import PreflightCheck, PreflightResult

BATCH_LOCKED_CODE = "BATCH_LOCKED"
PREFLIGHT_FAILED_CODE = "PREFLIGHT_FAILED"
ALREADY_LOCKED_CODE = "BATCH_ALREADY_LOCKED"

# Totals copied into the sign-off record. Amounts are kept as decimal strings.
_CLOSING_AMOUNT_KEYS = (
    "total_ingested_amount",
    "total_reconciled_amount",
    "total_credit_amount",
    "total_debit_amount",
    "net_ingested_amount",
    "total_unresolved_variance",
)
_CLOSING_COUNT_KEYS = ("total_records", "matched_count", "suggested_count", "conflict_count", "exception_count")


class BatchLockedError(HTTPException):
    """HTTP 423: the batch was signed off and its ledger is now read-only."""

    def __init__(self, batch_id: str, locked_by: str | None = None, locked_at: datetime | None = None):
        detail = {
            "code": BATCH_LOCKED_CODE,
            "message": f"Batch '{batch_id}' is locked and signed off. The ledger is read-only.",
            "details": {
                "batch_id": batch_id,
                "locked_by": locked_by,
                "locked_at": locked_at.isoformat() if locked_at else None,
            },
        }
        super().__init__(status_code=status.HTTP_423_LOCKED, detail=detail)


async def ensure_batch_unlocked(repo: ReconciliationRepository, batch_id: str) -> None:
    """Raise BatchLockedError (423) if the batch has been signed off."""
    batch = await repo.get_locked_batch(batch_id)
    if batch is not None:
        raise BatchLockedError(batch_id, batch.locked_by, batch.locked_at)


async def guard_batch_unlocked(batch_id: str = "default", db: AsyncSession = Depends(get_db)) -> None:
    """Route dependency for endpoints that carry the batch id in the path."""
    await ensure_batch_unlocked(ReconciliationRepository(db), batch_id)


async def guard_record_unlocked(record_id: str, db: AsyncSession = Depends(get_db)) -> None:
    """Route dependency for /records/{record_id}/... writes: looks up the record's batch first."""
    repo = ReconciliationRepository(db)
    batch_id = await repo.get_batch_id_for_log(record_id)
    if batch_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")
    await ensure_batch_unlocked(repo, batch_id)


def evaluate_preflight(summary: dict) -> PreflightResult:
    """Run the three audit preconditions against the live batch summary metrics."""
    variance = Decimal(summary["total_unresolved_variance"])
    conflicts = summary["conflict_count"]
    pending = summary["pending_count"]
    records = summary["total_records"]

    if records == 0:
        balance_detail = "The batch has no records to close."
    elif variance == Decimal("0.00"):
        balance_detail = "Trial balance difference is INR 0.00."
    else:
        balance_detail = (
            f"Trial balance difference is INR {variance:,.2f}: {summary['exception_count']} exception, "
            f"{summary['suggested_count']} suggested, {conflicts} conflict and {pending} pending rows are not reconciled."
        )

    checks = [
        PreflightCheck(
            id="NO_CONFLICTS",
            label="Zero unresolved CONFLICT records",
            passed=conflicts == 0,
            detail="No open conflicts." if conflicts == 0 else f"{conflicts} unresolved CONFLICT record(s).",
        ),
        PreflightCheck(
            id="NO_PENDING_SETTLEMENT",
            label="Zero items awaiting gateway settlement data",
            passed=pending == 0,
            detail=(
                "Nothing waiting on gateway sync."
                if pending == 0
                else f"{pending} record(s) still waiting for settlement data."
            ),
        ),
        PreflightCheck(
            id="TRIAL_BALANCE",
            label="Trial balance is in balance (difference = INR 0.00)",
            passed=records > 0 and variance == Decimal("0.00"),
            detail=balance_detail,
        ),
    ]
    return PreflightResult(
        can_lock=all(c.passed for c in checks),
        checks=checks,
        unresolved_variance=variance,
    )


def build_closing_totals(summary: dict) -> dict:
    totals: dict = {k: summary[k] for k in _CLOSING_COUNT_KEYS}
    totals.update({k: str(Decimal(summary[k])) for k in _CLOSING_AMOUNT_KEYS})
    return totals


async def lock_batch(
    repo: ReconciliationRepository, batch_id: str, locked_by: str, lock_note: str | None
) -> ReconciliationBatch:
    """Validate the pre-flight checks, then freeze the batch with the auditor's sign-off."""
    existing = await repo.get_batch(batch_id)
    if existing is not None and existing.is_locked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": ALREADY_LOCKED_CODE,
                "message": f"Batch '{batch_id}' was already signed off by {existing.locked_by}.",
            },
        )

    summary = await repo.get_summary_metrics(batch_id)
    preflight = evaluate_preflight(summary)
    if not preflight.can_lock:
        failed = [c for c in preflight.checks if not c.passed]
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": PREFLIGHT_FAILED_CODE,
                "message": "Pre-flight audit checks failed: " + "; ".join(c.detail for c in failed),
                "details": [c.model_dump() for c in failed],
            },
        )

    batch = existing or ReconciliationBatch(batch_id=batch_id)
    batch.is_locked = True
    batch.locked_at = datetime.now(UTC)
    batch.locked_by = locked_by
    batch.lock_note = lock_note
    batch.closing_totals = build_closing_totals(summary)
    repo.session.add(batch)
    try:
        await repo.session.flush()
    except IntegrityError as exc:
        # Two sign-offs raced; the other one won the primary key.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": ALREADY_LOCKED_CODE, "message": f"Batch '{batch_id}' was already signed off."},
        ) from exc
    return batch
