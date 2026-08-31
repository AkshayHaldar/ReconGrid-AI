"""Reconciliation Ledger and Approval API Routes."""

import csv
import io
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.reconciliation_log import ReconciliationLog
from app.repositories.reconciliation_repo import ReconciliationRepository
from app.repositories.settlement_repo import SettlementRepository
from app.schemas.common import ApiResponse
from app.schemas.reconciliation import (
    ActionRequest,
    ConflictResolveRequest,
    ReconciliationRecordItem,
    ReconciliationRecordListResponse,
    ReconciliationStatusResponse,
    ScorecardResponse,
)
from app.utils.money import to_decimal

router = APIRouter(prefix="/reconciliation", tags=["Reconciliation Ledger"])


def _map_log_to_item(log: ReconciliationLog) -> ReconciliationRecordItem:
    """Helper to map a DB ReconciliationLog to API response schema."""
    bank = log.bank_transaction
    rzp = log.rzp_settlement

    return ReconciliationRecordItem(
        id=log.id,
        batch_id=log.batch_id,
        bank_tx_id=log.bank_tx_id,
        date=bank.date if bank else log.matched_at,
        bank_utr=bank.utr if bank else None,
        bank_description=bank.description if bank else "",
        bank_amount=to_decimal(bank.amount) if bank else to_decimal(0),
        bank_direction=bank.direction if bank else "CREDIT",
        rzp_settlement_db_id=rzp.id if rzp else None,
        rzp_settlement_id=rzp.settlement_id if rzp else None,
        rzp_amount=to_decimal(rzp.amount) if rzp else None,
        rzp_gross_amount=to_decimal(rzp.gross_amount) if rzp else None,
        rzp_fees=to_decimal(rzp.fees) if rzp else None,
        rzp_tax=to_decimal(rzp.tax) if rzp else None,
        rzp_utr=rzp.utr if rzp else None,
        match_status=log.match_status,  # type: ignore
        match_tier=log.match_tier,  # type: ignore
        confidence_score=log.confidence_score,
        delta_amount=to_decimal(log.delta_amount),
        diagnostic_type=log.diagnostic_type,  # type: ignore
        diagnostic_note=log.diagnostic_note,
        matched_at=log.matched_at,
        human_action=log.human_action,
        raw_csv_row=bank.raw_csv_row if bank else None,
        raw_rzp_payload=rzp.raw_payload if rzp else None,
    )


@router.get("/{batch_id}/status", response_model=ApiResponse[ReconciliationStatusResponse])
async def get_batch_status(
    batch_id: str = "default",
    db: AsyncSession = Depends(get_db),
):
    """Returns aggregated summary metrics for Ramesh's dashboard cards."""
    repo = ReconciliationRepository(db)
    summary = await repo.get_summary_metrics(batch_id)
    return ApiResponse.ok(ReconciliationStatusResponse(**summary))


@router.get("/{batch_id}/scorecard", response_model=ApiResponse[ScorecardResponse])
async def get_batch_scorecard(
    batch_id: str = "default",
    db: AsyncSession = Depends(get_db),
):
    """Returns audit-grade scorecard metrics with separate Tier 0/1/2/3 breakdown,

    measured throughput (rows/sec), zero-float Decimal math, and complete unfiltered exception list.
    """
    repo = ReconciliationRepository(db)
    scorecard = await repo.get_scorecard_metrics(batch_id)
    return ApiResponse.ok(ScorecardResponse(**scorecard))


@router.get("/{batch_id}/records", response_model=ApiResponse[ReconciliationRecordListResponse])
async def get_reconciliation_records(
    batch_id: str = "default",
    status: str = Query(default="ALL", description="Filter by MATCHED, SUGGESTED, CONFLICT, EXCEPTION, PENDING_SETTLEMENT_DATA, or ALL"),
    q: str = Query(default="", description="Search query across UTR, descriptor, or settlement ID"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Returns filtered, paginated reconciliation records for the ledger table."""
    repo = ReconciliationRepository(db)
    logs, total_count = await repo.get_active_logs(
        batch_id=batch_id,
        status_filter=status,
        search=q,
        page=page,
        page_size=page_size,
    )
    records = [_map_log_to_item(l) for l in logs]

    return ApiResponse.ok(
        ReconciliationRecordListResponse(
            batch_id=batch_id,
            records=records,
            total_count=total_count,
            page=page,
            page_size=page_size,
        )
    )


@router.post("/records/{record_id}/approve", response_model=ApiResponse[ReconciliationRecordItem])
async def approve_suggested_match(
    record_id: str,
    action_req: ActionRequest = ActionRequest(),
    db: AsyncSession = Depends(get_db),
):
    """Single-click human approval for a SUGGESTED match."""
    repo = ReconciliationRepository(db)
    log = await repo.get_by_id(record_id)
    if not log:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")

    log.match_status = "MATCHED"
    log.human_action = "APPROVED"
    log.diagnostic_note += f" [Approved by CA{': ' + action_req.note if action_req.note else ''}]"
    await db.flush()

    return ApiResponse.ok(_map_log_to_item(log))


@router.post("/records/{record_id}/deny", response_model=ApiResponse[ReconciliationRecordItem])
async def deny_suggested_match(
    record_id: str,
    action_req: ActionRequest = ActionRequest(),
    db: AsyncSession = Depends(get_db),
):
    """Single-click human dismissal of a SUGGESTED match -> moves to EXCEPTION."""
    repo = ReconciliationRepository(db)
    log = await repo.get_by_id(record_id)
    if not log:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")

    log.match_status = "EXCEPTION"
    log.human_action = "DENIED"
    log.diagnostic_type = "UNRESOLVED"
    log.diagnostic_note = f"Human CA rejected suggestion{': ' + action_req.note if action_req.note else ''}"
    await db.flush()

    return ApiResponse.ok(_map_log_to_item(log))


@router.post("/records/{record_id}/resolve-conflict", response_model=ApiResponse[ReconciliationRecordItem])
async def resolve_conflict(
    record_id: str,
    resolve_req: ConflictResolveRequest,
    db: AsyncSession = Depends(get_db),
):
    """Resolves a CONFLICT by binding to the chosen settlement ID or dismissing the match."""
    repo = ReconciliationRepository(db)
    setl_repo = SettlementRepository(db)

    log = await repo.get_by_id(record_id)
    if not log:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")

    chosen_setl_id = resolve_req.chosen_settlement_id.strip() if resolve_req.chosen_settlement_id else ""

    # Case A: User chose to dismiss / unlink this conflict without matching
    if chosen_setl_id.upper() in {"NONE", "DISMISS", "UNLINK", "EXCEPTION"}:
        log.match_status = "EXCEPTION"
        log.human_action = "DISMISSED"
        log.diagnostic_type = "UNRESOLVED"
        log.rzp_settlement_id = None
        log.confidence_score = None
        bank_amt = to_decimal(log.bank_transaction.amount) if log.bank_transaction else to_decimal(0)
        log.delta_amount = bank_amt
        log.diagnostic_note = f"Conflict dismissed by CA: unlinked from settlement.{': ' + resolve_req.note if resolve_req.note else ''}"
        await db.flush()
        return ApiResponse.ok(_map_log_to_item(log))

    # Case B: Resolve by linking to chosen settlement
    target_setl = await setl_repo.get_by_settlement_id(chosen_setl_id)
    if not target_setl:
        target_setl = await setl_repo.get_by_id(chosen_setl_id)

    if not target_setl and log.rzp_settlement:
        if log.rzp_settlement.settlement_id == chosen_setl_id or log.rzp_settlement.id == chosen_setl_id:
            target_setl = log.rzp_settlement

    if not target_setl:
        # Fallback if synthetic identifier passed directly
        log.match_status = "MATCHED"
        log.human_action = "RESOLVED"
        log.diagnostic_note = f"Conflict manually resolved to {chosen_setl_id}.{': ' + resolve_req.note if resolve_req.note else ''}"
        await db.flush()
        return ApiResponse.ok(_map_log_to_item(log))

    # Link the chosen settlement to this log
    log.rzp_settlement_id = target_setl.id
    log.match_status = "MATCHED"
    log.human_action = "RESOLVED"
    log.confidence_score = 1.00
    bank_amt = to_decimal(log.bank_transaction.amount) if log.bank_transaction else to_decimal(0)
    log.delta_amount = abs(bank_amt - to_decimal(target_setl.amount))
    log.diagnostic_note = f"Conflict manually resolved to {target_setl.settlement_id}.{': ' + resolve_req.note if resolve_req.note else ''}"

    # Unlock and transition competing CONFLICT records in the same batch
    competing_logs = await repo.get_competing_conflict_logs(
        batch_id=log.batch_id,
        settlement_db_id=target_setl.id,
        exclude_log_id=log.id,
    )
    for comp in competing_logs:
        comp.match_status = "EXCEPTION"
        comp.human_action = "AUTO_DISPLACED"
        comp.diagnostic_type = "UNRESOLVED"
        comp.rzp_settlement_id = None
        comp.confidence_score = None
        comp_amt = to_decimal(comp.bank_transaction.amount) if comp.bank_transaction else to_decimal(0)
        comp.delta_amount = comp_amt
        bank_ref = (
            log.bank_transaction.utr
            or (f"ID:{log.bank_tx_id[:8]}" if log.bank_tx_id else "another row")
        ) if log.bank_transaction else log.id
        comp.diagnostic_note = (
            f"Settlement {target_setl.settlement_id} was manually allocated to bank row ({bank_ref}). "
            f"Transferred to EXCEPTION for separate audit."
        )

    await db.flush()
    refreshed_log = await repo.get_by_id(log.id)
    return ApiResponse.ok(_map_log_to_item(refreshed_log or log))


@router.get("/{batch_id}/export")
async def export_reconciliation_csv(
    batch_id: str = "default",
    db: AsyncSession = Depends(get_db),
):
    """Generates and downloads a complete reconciliation audit ledger CSV."""
    repo = ReconciliationRepository(db)
    logs, _ = await repo.get_active_logs(batch_id=batch_id, page=1, page_size=10000)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Date",
        "Direction",
        "Bank Description",
        "Bank UTR",
        "Bank Amount (INR)",
        "Razorpay Settlement ID",
        "Razorpay Net (INR)",
        "Razorpay Gross (INR)",
        "Fees (INR)",
        "GST (INR)",
        "Match Status",
        "Match Tier",
        "Confidence %",
        "Diagnostic Type",
        "Diagnostic Note",
        "Human Action",
    ])

    for log in logs:
        bank = log.bank_transaction
        rzp = log.rzp_settlement
        writer.writerow([
            bank.date.strftime("%Y-%m-%d") if bank else "",
            bank.direction if bank else "CREDIT",
            bank.description if bank else "",
            bank.utr if bank else "",
            f"{to_decimal(bank.amount):.2f}" if bank else "0.00",
            rzp.settlement_id if rzp else "",
            f"{to_decimal(rzp.amount):.2f}" if rzp else "",
            f"{to_decimal(rzp.gross_amount):.2f}" if rzp else "",
            f"{to_decimal(rzp.fees):.2f}" if rzp else "",
            f"{to_decimal(rzp.tax):.2f}" if rzp else "",
            log.match_status,
            log.match_tier,
            f"{log.confidence_score * 100:.1f}%" if log.confidence_score is not None else ("100.0%" if log.match_status == "MATCHED" else "N/A"),
            log.diagnostic_type,
            log.diagnostic_note,
            log.human_action or "AUTO",
        ])

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=recongrid_audit_{batch_id}.csv"},
    )
