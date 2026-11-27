"""Reconciliation Ledger and Approval API Routes."""

import csv
import io
import json
import re
from dataclasses import asdict
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.reconciliation_log import ReconciliationLog
from app.repositories.reconciliation_repo import ReconciliationRepository
from app.repositories.settlement_repo import SettlementRepository
from app.schemas.common import ApiResponse
from app.schemas.reconciliation import (
    ActionRequest,
    BatchApproveRequest,
    BatchApproveResponse,
    ConflictResolveRequest,
    ReconciliationRecordItem,
    ReconciliationRecordListResponse,
    ReconciliationStatusResponse,
    ScorecardResponse,
)
from app.services.diagnostics import DiagnosticsService
from app.services.export_service import XLSX_MEDIA_TYPE, build_reconciliation_workbook
from app.services.reconciliation import build_audit_certificate, verify_batch_audit_chain
from app.services.tally_export import (
    BANK_LEDGER,
    CLEARING_LEDGER,
    GATEWAY_CHARGES_LEDGER,
    INPUT_GST_LEDGER,
    build_tally_xml,
)
from app.services.tax_schedule import tax_schedule_csv_rows
from app.utils.money import to_decimal

router = APIRouter(prefix="/reconciliation", tags=["Reconciliation Ledger"])


def _csv_text(value: str | None) -> str:
    """Keep exported text literal when spreadsheet apps interpret CSV cells."""
    text = value or ""
    if text and (text[0] in "=+-@\t\r\n" or text.lstrip(" \t\r\n\v\f\ufeff").startswith(("=", "+", "-", "@"))):
        return "'" + text
    return text


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
    """Returns aggregated summary metrics for the dashboard summary cards."""
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


@router.get("/{batch_id}/verify-audit-chain")
async def verify_audit_chain(
    batch_id: str = "default",
    db: AsyncSession = Depends(get_db),
):
    """Recomputes the SHA-256 audit chain of the batch and reports the first tampered or missing row, if any."""
    result = await verify_batch_audit_chain(ReconciliationRepository(db), batch_id)
    return ApiResponse.ok(asdict(result))


@router.get("/{batch_id}/audit-certificate")
async def export_audit_certificate(
    batch_id: str = "default",
    db: AsyncSession = Depends(get_db),
):
    """Downloads a JSON Audit Compliance Certificate for the batch (HMAC-signed when AUDIT_SIGNING_KEY is set)."""
    result = await verify_batch_audit_chain(ReconciliationRepository(db), batch_id)
    certificate = build_audit_certificate(batch_id, result, settings.AUDIT_SIGNING_KEY)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", batch_id)
    return Response(
        content=json.dumps(certificate, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=recongrid_audit_certificate_{safe_name}.json"},
    )


@router.get("/{batch_id}/records", response_model=ApiResponse[ReconciliationRecordListResponse])
async def get_reconciliation_records(
    batch_id: str = "default",
    status: str = Query(
        default="ALL", description="Filter by MATCHED, SUGGESTED, CONFLICT, EXCEPTION, PENDING_SETTLEMENT_DATA, or ALL"
    ),
    q: str = Query(default="", description="Search query across UTR, descriptor, or settlement ID"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None, max_length=2048),
    limit: int | None = Query(default=None, ge=1, le=200),
    diagnostic: str = Query(default="ALL", max_length=64),
    sort: Literal["date", "bank_amount", "rzp_amount", "delta_amount", "bank_utr"] = "date",
    direction: Literal["asc", "desc"] = "desc",
    anchor_id: str | None = Query(default=None, max_length=36),
    settlement_id: str = Query(default="", max_length=36),
    from_date: str | None = Query(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="Filter from date (YYYY-MM-DD) in IST"
    ),
    to_date: str | None = Query(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="Filter to date (YYYY-MM-DD) in IST"
    ),
    db: AsyncSession = Depends(get_db),
):
    """Returns filtered, paginated reconciliation records for the ledger table."""
    # Validate before either pagination path; regex alone accepts February 31.
    for value in (from_date, to_date):
        if value is not None:
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Invalid calendar date; use YYYY-MM-DD.") from exc
    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=400, detail="Start date must not be after end date.")
    repo = ReconciliationRepository(db)
    next_cursor, has_more = None, False
    if limit is not None or cursor is not None or anchor_id is not None:
        try:
            logs, total_count, next_cursor, has_more = await repo.get_log_window(
                batch_id,
                status,
                q,
                diagnostic,
                sort,
                direction,
                limit or page_size,
                cursor,
                anchor_id,
                settlement_id,
                from_date,
                to_date,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    else:
        logs, total_count = await repo.get_active_logs(
            batch_id=batch_id,
            status_filter=status,
            search=q,
            page=page,
            page_size=page_size,
            from_date=from_date,
            to_date=to_date,
        )
    records = [_map_log_to_item(l) for l in logs]

    return ApiResponse.ok(
        ReconciliationRecordListResponse(
            batch_id=batch_id,
            records=records,
            total_count=total_count,
            page=page,
            page_size=limit or page_size,
            next_cursor=next_cursor,
            has_more=has_more,
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


@router.post("/{batch_id}/batch-approve", response_model=ApiResponse[BatchApproveResponse])
async def batch_approve_suggested_matches(
    batch_id: str,
    request: BatchApproveRequest,
    db: AsyncSession = Depends(get_db),
):
    """Approve high-confidence active suggestions with one database update."""
    repo = ReconciliationRepository(db)
    count = await repo.batch_approve_suggestions(batch_id, request.min_confidence)
    return ApiResponse.ok(BatchApproveResponse(approved_count=count, batch_id=batch_id))


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


@router.post("/records/{record_id}/revert", response_model=ApiResponse[ReconciliationRecordItem])
async def revert_human_action(
    record_id: str,
    action_req: ActionRequest = ActionRequest(),
    db: AsyncSession = Depends(get_db),
):
    """Reverts a human APPROVED or DENIED action back to SUGGESTED."""
    repo = ReconciliationRepository(db)
    log = await repo.get_by_id(record_id)
    if not log:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")
    if log.human_action not in ("APPROVED", "DENIED"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only approved or denied suggestions can be reverted.",
        )

    log.match_status = "SUGGESTED"
    log.human_action = None
    if log.diagnostic_type == "UNRESOLVED" and log.rzp_settlement_id is not None:
        if log.match_tier == "TIER_0":
            log.diagnostic_type = "DATE_AMOUNT_FALLBACK"
        elif log.match_tier == "TIER_2":
            log.diagnostic_type = "FUZZY_MATCH"
        else:
            log.diagnostic_type = "EXACT_MATCH"
    log.diagnostic_note += f" [Reverted by CA{': ' + action_req.note if action_req.note else ''}]"
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
        log.diagnostic_note = (
            f"Conflict dismissed by CA: unlinked from settlement.{': ' + resolve_req.note if resolve_req.note else ''}"
        )
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
        log.diagnostic_note = (
            f"Conflict manually resolved to {chosen_setl_id}.{': ' + resolve_req.note if resolve_req.note else ''}"
        )
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
            (log.bank_transaction.utr or (f"ID:{log.bank_tx_id[:8]}" if log.bank_tx_id else "another row"))
            if log.bank_transaction
            else log.id
        )
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
    writer.writerow(
        [
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
        ]
    )

    for log in logs:
        bank = log.bank_transaction
        rzp = log.rzp_settlement
        writer.writerow(
            [
                bank.date.strftime("%Y-%m-%d") if bank else "",
                _csv_text(bank.direction) if bank else "CREDIT",
                _csv_text(bank.description) if bank else "",
                _csv_text(bank.utr) if bank else "",
                f"{to_decimal(bank.amount):.2f}" if bank else "0.00",
                _csv_text(rzp.settlement_id) if rzp else "",
                f"{to_decimal(rzp.amount):.2f}" if rzp else "",
                f"{to_decimal(rzp.gross_amount):.2f}" if rzp else "",
                f"{to_decimal(rzp.fees):.2f}" if rzp else "",
                f"{to_decimal(rzp.tax):.2f}" if rzp else "",
                _csv_text(log.match_status),
                _csv_text(log.match_tier),
                (
                    f"{log.confidence_score * 100:.1f}%"
                    if log.confidence_score is not None
                    else ("100.0%" if log.match_status == "MATCHED" else "N/A")
                ),
                _csv_text(log.diagnostic_type),
                _csv_text(log.diagnostic_note),
                _csv_text(log.human_action) or "AUTO",
            ]
        )

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=recongrid_audit_{batch_id}.csv"},
    )


@router.get("/{batch_id}/export-xlsx")
async def export_reconciliation_xlsx(
    batch_id: str = "default",
    db: AsyncSession = Depends(get_db),
):
    """Downloads a styled Excel workbook: summary, reconciled ledger and exceptions."""
    repo = ReconciliationRepository(db)
    logs, _ = await repo.get_active_logs(batch_id=batch_id, page=1, page_size=10000)
    content = build_reconciliation_workbook(batch_id, logs)
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f"attachment; filename=recongrid_audit_{batch_id}.xlsx"},
    )


@router.get("/{batch_id}/export-tally-xml")
async def export_tally_xml(
    batch_id: str = "default",
    bank_ledger: str = Query(default=BANK_LEDGER, min_length=1, max_length=255),
    charges_ledger: str = Query(default=GATEWAY_CHARGES_LEDGER, min_length=1, max_length=255),
    gst_ledger: str = Query(default=INPUT_GST_LEDGER, min_length=1, max_length=255),
    clearing_ledger: str = Query(default=CLEARING_LEDGER, min_length=1, max_length=255),
    db: AsyncSession = Depends(get_db),
):
    """Downloads matched settlements as balanced Tally Prime Journal vouchers."""
    repo = ReconciliationRepository(db)
    logs, _ = await repo.get_active_logs(batch_id=batch_id, page=1, page_size=10000)
    try:
        export = build_tally_xml(
            logs,
            bank_ledger=bank_ledger,
            charges_ledger=charges_ledger,
            gst_ledger=gst_ledger,
            clearing_ledger=clearing_ledger,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return Response(
        content=export.xml,
        media_type="application/xml",
        headers={
            "Content-Disposition": "attachment; filename=reconciliation_tally_vouchers.xml",
            "X-Skipped-Vouchers": str(len(export.skipped)),
        },
    )


async def _all_active_logs(repo: ReconciliationRepository, batch_id: str, page_size: int = 1000):
    """Every active log in the batch, fetched page by page so large batches are not truncated."""
    logs: list = []
    page = 1
    while True:
        chunk, total = await repo.get_active_logs(batch_id=batch_id, page=page, page_size=page_size)
        logs.extend(chunk)
        if not chunk or len(logs) >= total:
            return logs
        page += 1


@router.get("/{batch_id}/tax-schedule")
async def get_tax_schedule(
    batch_id: str = "default",
    intra_state: bool = Query(True, description="Split GST into CGST+SGST (true) or report it as IGST (false)"),
    db: AsyncSession = Depends(get_db),
):
    """Section 194-O TDS and GST input tax credit totals for the batch, with TDS deviations."""
    logs = await _all_active_logs(ReconciliationRepository(db), batch_id)
    schedule = DiagnosticsService.calculate_batch_tax_schedule(batch_id, logs, intra_state=intra_state)
    return ApiResponse.ok(asdict(schedule))


@router.get("/{batch_id}/tax-schedule/export")
async def export_tax_schedule(
    batch_id: str = "default",
    intra_state: bool = Query(True, description="Split GST into CGST+SGST (true) or report it as IGST (false)"),
    db: AsyncSession = Depends(get_db),
):
    """CSV of the tax schedule with a CA signature and UDIN attestation block."""
    logs = await _all_active_logs(ReconciliationRepository(db), batch_id)
    schedule = DiagnosticsService.calculate_batch_tax_schedule(batch_id, logs, intra_state=intra_state)
    output = io.StringIO()
    csv.writer(output).writerows(tax_schedule_csv_rows(schedule, _csv_text))
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=recongrid_tax_schedule_{batch_id}.csv"},
    )


@router.get("/{batch_id}/scorecard/export")
async def export_scorecard_report(
    batch_id: str = "default",
    db: AsyncSession = Depends(get_db),
):
    """Generates and downloads a formal Chartered Accountant reconciliation scorecard report."""
    repo = ReconciliationRepository(db)
    scorecard = await repo.get_scorecard_metrics(batch_id=batch_id)

    lines = [
        "=" * 90,
        f"RECONGRID AI - FORMAL RECONCILIATION AUDIT SCORECARD (BATCH: {batch_id.upper()})",
        "=" * 90,
        f"Generated At: {scorecard.get('batch_id', batch_id)}",
        f"Throughput:   {scorecard['rows_per_second']} rows/sec (Wall time: {scorecard['processing_time_seconds']}s)",
        f"Conservation: {'100% CONSERVED (0 lost)' if scorecard['is_fully_accounted'] else 'UNBALANCED'}",
        "-" * 90,
        "1. SUMMARY TOTALS & RECONCILIATION RATE",
        f"   Total Bank Ingested Rows:     {scorecard['total_rows_processed']:>8d}  |  Amount: INR {scorecard['total_ingested_amount']:>14,.2f}",
        f"   Total Reconciled Amount:      {scorecard['total_matched_count']:>8d}  |  Amount: INR {scorecard['total_reconciled_amount']:>14,.2f}",
        f"   Total Exception Amount:       {scorecard['total_exception_count']:>8d}  |  Amount: INR {scorecard['total_exception_amount']:>14,.2f}",
        f"   Total Pending Amount:         {scorecard['total_pending_count']:>8d}  |  Amount: INR {scorecard['total_pending_amount']:>14,.2f}",
        f"   Overall Net Match Rate:       {scorecard['total_matched_percentage']:>8.2f}%",
        "-" * 90,
        "2. TIERED RESOLUTION BREAKDOWN",
        f"   - Tier 1 (Exact & Normalized UTR): {scorecard['tier_1_count']:>6d} rows ({scorecard['tier_1_percentage']}%)",
        f"   - Tier 2 (Fuzzy Descriptor >=90%): {scorecard['tier_2_count']:>6d} rows ({scorecard['tier_2_percentage']}%)",
        f"   - Tier 0 (Date Window Fallback):   {scorecard['tier_0_count']:>6d} rows ({scorecard['tier_0_percentage']}%)",
        f"   - Tier 3 (Diagnostic & Subset-Sum):{scorecard['tier_3_count']:>6d} rows ({scorecard['tier_3_percentage']}%)",
        "-" * 90,
        "3. UNRESOLVED ANOMALIES & AUDIT VARIANCE",
        f"   Total Residual Exceptions: {len(scorecard['exceptions'])}",
        "",
        f"{'Row #':<6} | {'Bank Tx ID':<12} | {'Amount (INR)':<14} | {'Reason Code':<22} | {'Diagnostic Note'}",
        "-" * 90,
    ]

    for idx, exc in enumerate(scorecard["exceptions"], 1):
        lines.append(
            f"{idx:<6d} | {str(exc['bank_transaction_id'])[:12]:<12} | "
            f"INR {exc['amount']:>10,.2f} | {exc['reason_code']:<22} | {exc['diagnostic_note']}"
        )

    lines.extend(
        [
            "=" * 90,
            "END OF AUDIT SCORECARD REPORT - RECONGRID AI ENGINE",
            "=" * 90,
        ]
    )

    report_text = "\n".join(lines)
    return Response(
        content=report_text,
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename=recongrid_scorecard_{batch_id}.txt"},
    )
