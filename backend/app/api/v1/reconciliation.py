"""Reconciliation Ledger and Approval API Routes."""

import csv
import io
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.reconciliation_log import ReconciliationLog
from app.repositories.reconciliation_repo import ReconciliationRepository
from app.schemas.common import ApiResponse
from app.schemas.reconciliation import (
    ActionRequest,
    ConflictResolveRequest,
    ReconciliationRecordItem,
    ReconciliationRecordListResponse,
    ReconciliationStatusResponse,
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


@router.get("/{batch_id}/records", response_model=ApiResponse[ReconciliationRecordListResponse])
async def get_reconciliation_records(
    batch_id: str = "default",
    status: str = Query(default="ALL", description="Filter by MATCHED, SUGGESTED, CONFLICT, EXCEPTION, or ALL"),
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
    """Resolves a CONFLICT by binding to the chosen settlement ID."""
    repo = ReconciliationRepository(db)
    log = await repo.get_by_id(record_id)
    if not log:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")

    log.match_status = "MATCHED"
    log.human_action = "RESOLVED"
    log.diagnostic_note = f"Conflict manually resolved to {resolve_req.chosen_settlement_id}."
    await db.flush()

    return ApiResponse.ok(_map_log_to_item(log))


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
            f"{log.confidence_score * 100:.1f}%" if log.confidence_score else "100%",
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
