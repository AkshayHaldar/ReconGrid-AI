"""Razorpay Webhook receiver API Route."""

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory, get_db
from app.core.logging import logger
from app.core.security import razorpay_webhook_guard
from app.models.webhook_event import ProcessedWebhookEvent
from app.repositories.bank_repo import BankRepository
from app.repositories.reconciliation_repo import ReconciliationRepository
from app.repositories.settlement_repo import SettlementRepository
from app.schemas.common import ApiResponse
from app.schemas.razorpay import RazorpayRefundPayload
from app.schemas.webhook import WebhookAckResponse, WebhookEventItem, WebhookHealth
from app.services.batch_lock import BatchLockedError
from app.services.reconciliation import ReconciliationEngine
from app.utils.money import paise_to_rupees

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

# Deliveries refused before they were accepted are stored with these statuses so the UI can show them.
REJECTED_SIGNATURE = "REJECTED_SIGNATURE"
REJECTED_MALFORMED = "REJECTED_MALFORMED"
REJECTED_STATUSES = (REJECTED_SIGNATURE, REJECTED_MALFORMED)
MAX_REJECTED_ROWS = 50  # unauthenticated callers can create these, so only the newest are kept
MAX_STORED_BODY_CHARS = 4096
IDLE_AFTER = timedelta(hours=24)
RECENT_EVENTS_DEFAULT = 15


def _as_utc(value: datetime) -> datetime:
    """SQLite hands back naive datetimes; everything stored here is UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def record_rejected_delivery(raw_body: bytes, reason: str) -> None:
    """Remember a refused delivery with its own session; never let bookkeeping change the 400."""
    try:
        # Refused bodies are attacker controlled: cap what is decoded and parsed before anything else.
        # A UTF-8 character is at most 4 bytes, so this window always holds the stored characters.
        window = raw_body[: MAX_STORED_BODY_CHARS * 4]
        text_body = window.decode("utf-8", errors="replace")
        truncated = len(raw_body) > len(window) or len(text_body) > MAX_STORED_BODY_CHARS
        event_type = "unknown"
        if len(raw_body) <= len(window):  # an oversized body is never parsed, so no event type for it
            try:
                parsed = json.loads(text_body)
                if isinstance(parsed, dict) and isinstance(parsed.get("event"), str):
                    event_type = parsed["event"][:64]
            except ValueError:
                pass
        row_id = "rej_" + hashlib.sha256(raw_body).hexdigest()[:60]
        now = datetime.now(UTC)
        async with async_session_factory() as db:
            existing = await db.scalar(
                select(ProcessedWebhookEvent).where(ProcessedWebhookEvent.razorpay_event_id == row_id)
            )
            if existing is not None:
                # The gateway retrying the same bad delivery only moves the timestamp.
                existing.received_at = now
                existing.processing_status = reason
            else:
                db.add(
                    ProcessedWebhookEvent(
                        razorpay_event_id=row_id,
                        event_type=event_type,
                        processing_status=reason,
                        payload={
                            "raw_body": text_body[:MAX_STORED_BODY_CHARS],
                            "truncated": truncated,
                        },
                        received_at=now,
                    )
                )
            await db.flush()
            keep = (
                select(ProcessedWebhookEvent.id)
                .where(ProcessedWebhookEvent.processing_status.in_(REJECTED_STATUSES))
                .order_by(ProcessedWebhookEvent.received_at.desc())
                .limit(MAX_REJECTED_ROWS)
            )
            await db.execute(
                delete(ProcessedWebhookEvent).where(
                    ProcessedWebhookEvent.processing_status.in_(REJECTED_STATUSES),
                    ProcessedWebhookEvent.id.not_in(keep),
                )
            )
            await db.commit()
    except Exception:
        logger.exception("webhook_rejection_record_failed", reason=reason)


async def recording_webhook_guard(
    request: Request,
    x_razorpay_signature: str = Header(default="", alias="X-Razorpay-Signature"),
) -> bytes:
    """razorpay_webhook_guard, plus a record of the delivery when the signature is refused."""
    try:
        return await razorpay_webhook_guard(request, x_razorpay_signature)
    except HTTPException:
        await record_rejected_delivery(await request.body(), REJECTED_SIGNATURE)
        raise


async def reconcile_webhook_event(event_id: str) -> None:
    """Process a committed event with a session owned by this background task."""
    async with async_session_factory() as db:
        try:
            # Serialize default-batch snapshots across API processes, not just coroutines.
            if db.get_bind().dialect.name == "postgresql":
                await db.execute(text("SELECT pg_advisory_xact_lock(1380405828)"))
            elif db.get_bind().dialect.name == "sqlite":
                await db.execute(text("BEGIN IMMEDIATE"))
            event = await db.scalar(
                select(ProcessedWebhookEvent).where(ProcessedWebhookEvent.razorpay_event_id == event_id)
            )
            if event is None or event.processing_status != "QUEUED":
                return
            settlement_repo = SettlementRepository(db)
            batch_ids: Sequence[str] = ["default"]
            if event.event_type == "refund.processed":
                entity = event.payload["payload"]["refund"]["entity"]
                refund = await settlement_repo.upsert_refund(RazorpayRefundPayload.model_validate(entity).to_record(entity))
                if not refund.settlement_id:
                    event.processing_status = "PROCESSED"
                    await db.commit()
                    return
                batch_ids = await settlement_repo.get_active_batches_for_settlement(refund.settlement_id) or batch_ids
            else:
                setl_data = event.payload["payload"]["settlement"]["entity"]
                amount_inr = paise_to_rupees(setl_data.get("amount", 0))
                fees_inr = paise_to_rupees(setl_data.get("fees", 0))
                tax_inr = paise_to_rupees(setl_data.get("tax", 0))
                created_ts = setl_data.get("created_at")
                dt = datetime.fromtimestamp(created_ts, UTC) if created_ts else datetime.now(UTC)
                await settlement_repo.upsert_settlement({
                    "settlement_id": setl_data.get("id")
                    or f"setl_{hashlib.sha256(event_id.encode()).hexdigest()[:59]}",
                    "amount": amount_inr,
                    "gross_amount": amount_inr + fees_inr + tax_inr,
                    "fees": fees_inr,
                    "tax": tax_inr,
                    "utr": setl_data.get("utr"),
                    "status": setl_data.get("status", "processed"),
                    "settlement_created_at": dt,
                    "raw_payload": setl_data,
                    "is_test_mode": True,
                })

            # Trigger immediate reconciliation
            bank_repo = BankRepository(db)
            recon_repo = ReconciliationRepository(db)
            engine = ReconciliationEngine(recon_repo)

            all_setls = await settlement_repo.get_all()
            for batch_id in batch_ids:
                bank_txs = await bank_repo.get_all_by_batch(batch_id)
                if not bank_txs:
                    continue
                try:
                    await engine.reconcile_batch(bank_txs, all_setls, batch_id=batch_id)
                except BatchLockedError:
                    # The settlement or refund is stored, but a signed-off period is never re-matched.
                    logger.warning(
                        "webhook_reconciliation_skipped_batch_locked", event_id=event_id, batch_id=batch_id
                    )
            event.processing_status = "PROCESSED"
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("webhook_reconciliation_failed", event_id=event_id)
            # Roll back partial settlement/reconciliation writes before marking failure.
            await db.execute(
                update(ProcessedWebhookEvent)
                .where(ProcessedWebhookEvent.razorpay_event_id == event_id)
                .values(processing_status="FAILED")
            )
            await db.commit()


@router.post("/razorpay", response_model=ApiResponse[WebhookAckResponse])
async def handle_razorpay_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    raw_body: bytes = Depends(recording_webhook_guard),
    db: AsyncSession = Depends(get_db),
):
    """Verify and commit the event before acknowledging; reconcile after response."""
    inr_refund = False
    try:
        payload = json.loads(raw_body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Webhook body must be an object")
        settlement = payload.get("payload", {}).get("settlement", {}).get("entity", {})
        if not isinstance(settlement, dict):
            raise ValueError("Settlement entity must be an object")
        if payload.get("event") == "settlement.processed" and not settlement:
            raise ValueError("Settlement events require an entity")
        if payload.get("event") == "refund.processed":
            refund_entity = payload.get("payload", {}).get("refund", {}).get("entity")
            refund = RazorpayRefundPayload.model_validate(refund_entity)
            if refund.status != "processed":
                raise ValueError("Processed refund events require a processed refund")
            inr_refund = refund.currency == "INR"
        settlement_id = settlement.get("id")
        if settlement_id is not None and (not isinstance(settlement_id, str) or len(settlement_id) > 64):
            raise ValueError("Invalid settlement ID")
    except (ValueError, UnicodeError, AttributeError):
        await record_rejected_delivery(raw_body, REJECTED_MALFORMED)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON webhook body")

    # Stable across processes and restarts, unlike Python's randomized hash().
    event_id = payload.get("id") or payload.get("event_id") or hashlib.sha256(raw_body).hexdigest()
    event_type = payload.get("event", "unknown")
    if not isinstance(event_id, str) or len(event_id) > 64 or not isinstance(event_type, str) or len(event_type) > 64:
        await record_rejected_delivery(raw_body, REJECTED_MALFORMED)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook event metadata")
    stmt = select(ProcessedWebhookEvent).where(ProcessedWebhookEvent.razorpay_event_id == event_id)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None and existing.processing_status == "FAILED":
        # Only one concurrent retry may claim a failed event.
        claimed = await db.scalar(
            update(ProcessedWebhookEvent)
            .where(ProcessedWebhookEvent.id == existing.id, ProcessedWebhookEvent.processing_status == "FAILED")
            .values(processing_status="QUEUED")
            .returning(ProcessedWebhookEvent.id)
        )
        await db.commit()
        if claimed is not None:
            background_tasks.add_task(reconcile_webhook_event, event_id)
            return ApiResponse.ok(
                WebhookAckResponse(status="queued", event_id=event_id, action_taken="RECONCILIATION_QUEUED")
            )
    if existing is not None:
        logger.info("duplicate_webhook_ignored", event_id=event_id, event_type=event_type)
        return ApiResponse.ok(WebhookAckResponse(status="ok", event_id=event_id, action_taken="DUPLICATE_IGNORED"))

    should_queue = event_type == "settlement.processed" or inr_refund
    db.add(
        ProcessedWebhookEvent(
            razorpay_event_id=event_id,
            event_type=event_type,
            processing_status="QUEUED" if should_queue else "PROCESSED",
            payload=payload,
            received_at=datetime.now(UTC),
        )
    )
    try:
        # The worker must see the event even if dependency teardown has not run.
        await db.commit()
    except IntegrityError:
        await db.rollback()
        if await db.scalar(stmt) is None:
            raise
        return ApiResponse.ok(WebhookAckResponse(status="ok", event_id=event_id, action_taken="DUPLICATE_IGNORED"))

    if should_queue:
        background_tasks.add_task(reconcile_webhook_event, event_id)
    return ApiResponse.ok(
        WebhookAckResponse(
            status="queued" if should_queue else "ok",
            event_id=event_id,
            action_taken="RECONCILIATION_QUEUED" if should_queue else "EVENT_RECORDED",
        )
    )


def _settlement_entity(payload: Any) -> dict[str, Any]:
    """Settlement entity of a stored payload, or {} when the payload is not shaped like one."""
    try:
        entity = payload["payload"]["settlement"]["entity"]
    except (KeyError, TypeError):
        return {}
    return entity if isinstance(entity, dict) else {}


def _event_item(event: ProcessedWebhookEvent) -> WebhookEventItem:
    entity = _settlement_entity(event.payload)
    settlement_id, utr = entity.get("id"), entity.get("utr")
    if event.processing_status == REJECTED_SIGNATURE:
        signature, ingestion = "INVALID", "REJECTED"
    elif event.processing_status == REJECTED_MALFORMED:
        # The signature matched, the body did not make sense.
        signature, ingestion = "MALFORMED", "REJECTED"
    elif event.processing_status == "FAILED":
        signature, ingestion = "VALID", "FAILED"
    elif event.event_type == "settlement.processed" and entity:
        signature, ingestion = "VALID", "RECONCILIATION_TRIGGERED"
    else:
        signature, ingestion = "VALID", "IGNORED"
    return WebhookEventItem(
        event_id=event.razorpay_event_id,
        event_type=event.event_type,
        received_at=_as_utc(event.received_at),
        settlement_id=settlement_id if isinstance(settlement_id, str) else None,
        utr=utr if isinstance(utr, str) else None,
        signature_status=signature,  # type: ignore[arg-type]
        ingestion_status=ingestion,  # type: ignore[arg-type]
        processing_status=event.processing_status,
        payload=event.payload if isinstance(event.payload, dict) else {},
    )


@router.get("/recent", response_model=ApiResponse[list[WebhookEventItem]])
async def list_recent_webhook_events(
    limit: int = Query(default=RECENT_EVENTS_DEFAULT, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Newest webhook deliveries first, including the ones refused for a bad signature or body."""
    stmt = (
        select(ProcessedWebhookEvent)
        .order_by(ProcessedWebhookEvent.received_at.desc(), ProcessedWebhookEvent.created_at.desc())
        .limit(limit)
    )
    events = (await db.execute(stmt)).scalars().all()
    return ApiResponse.ok([_event_item(event) for event in events])


@router.get("/health", response_model=ApiResponse[WebhookHealth])
async def webhook_health(db: AsyncSession = Depends(get_db)):
    """Heartbeat for the header: live, idle, or warning when the newest delivery was refused."""
    rejected = ProcessedWebhookEvent.processing_status.in_(REJECTED_STATUSES)
    last_verified = await db.scalar(select(func.max(ProcessedWebhookEvent.received_at)).where(~rejected))
    last_rejected = await db.scalar(select(func.max(ProcessedWebhookEvent.received_at)).where(rejected))
    last_verified = _as_utc(last_verified) if last_verified else None
    last_rejected = _as_utc(last_rejected) if last_rejected else None
    now = datetime.now(UTC)

    reason = None
    if last_rejected is not None:
        reason_status = await db.scalar(
            select(ProcessedWebhookEvent.processing_status)
            .where(rejected)
            .order_by(ProcessedWebhookEvent.received_at.desc())
            .limit(1)
        )
        reason = "INVALID_SIGNATURE" if reason_status == REJECTED_SIGNATURE else "MALFORMED_PAYLOAD"

    rejection_is_current = (
        last_rejected is not None
        and now - last_rejected <= IDLE_AFTER
        and (last_verified is None or last_rejected > last_verified)
    )
    if rejection_is_current:
        pulse = "warning"
        message = (
            "Webhook Signature Verification Failed. Verify the webhook secret in Settings."
            if reason == "INVALID_SIGNATURE"
            else "A webhook was rejected because its payload was malformed."
        )
    elif last_verified is not None and now - last_verified <= IDLE_AFTER:
        pulse, message = "live", "Verified webhook received in the last 24 hours."
    else:
        pulse, message = "idle", "No webhook received in the last 24 hours."
    return ApiResponse.ok(
        WebhookHealth(
            status=pulse,  # type: ignore[arg-type]
            last_verified_at=last_verified,
            last_rejected_at=last_rejected,
            last_rejection_reason=reason,  # type: ignore[arg-type]
            message=message,
        )
    )
