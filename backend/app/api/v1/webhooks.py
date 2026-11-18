"""Razorpay Webhook receiver API Route."""

import hashlib
import json
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import select, text, update
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
from app.schemas.webhook import WebhookAckResponse
from app.services.reconciliation import ReconciliationEngine
from app.utils.money import paise_to_rupees

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


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
            setl_data = event.payload["payload"]["settlement"]["entity"]
            amount_inr = paise_to_rupees(setl_data.get("amount", 0))
            fees_inr = paise_to_rupees(setl_data.get("fees", 0))
            tax_inr = paise_to_rupees(setl_data.get("tax", 0))
            gross_inr = amount_inr + fees_inr + tax_inr

            created_ts = setl_data.get("created_at")
            dt = datetime.fromtimestamp(created_ts, UTC) if created_ts else datetime.now(UTC)

            settlement_repo = SettlementRepository(db)
            setl_obj, _ = await settlement_repo.upsert_settlement(
                {
                    "settlement_id": setl_data.get("id")
                    or f"setl_{hashlib.sha256(event_id.encode()).hexdigest()[:59]}",
                    "amount": amount_inr,
                    "gross_amount": gross_inr,
                    "fees": fees_inr,
                    "tax": tax_inr,
                    "utr": setl_data.get("utr"),
                    "status": setl_data.get("status", "processed"),
                    "settlement_created_at": dt,
                    "raw_payload": setl_data,
                    "is_test_mode": True,
                }
            )

            # Trigger immediate reconciliation
            bank_repo = BankRepository(db)
            recon_repo = ReconciliationRepository(db)
            engine = ReconciliationEngine(recon_repo)

            bank_txs = await bank_repo.get_all_by_batch("default")
            all_setls = await settlement_repo.get_all()
            if bank_txs:
                await engine.reconcile_batch(bank_txs, all_setls, batch_id="default")
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
    raw_body: bytes = Depends(razorpay_webhook_guard),
    db: AsyncSession = Depends(get_db),
):
    """Verify and commit the event before acknowledging; reconcile after response."""
    try:
        payload = json.loads(raw_body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Webhook body must be an object")
        settlement = payload.get("payload", {}).get("settlement", {}).get("entity", {})
        if not isinstance(settlement, dict):
            raise ValueError("Settlement entity must be an object")
        if payload.get("event") == "settlement.processed" and not settlement:
            raise ValueError("Settlement events require an entity")
        settlement_id = settlement.get("id")
        if settlement_id is not None and (not isinstance(settlement_id, str) or len(settlement_id) > 64):
            raise ValueError("Invalid settlement ID")
    except (ValueError, UnicodeError, AttributeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON webhook body")

    # Stable across processes and restarts, unlike Python's randomized hash().
    event_id = payload.get("id") or payload.get("event_id") or hashlib.sha256(raw_body).hexdigest()
    event_type = payload.get("event", "unknown")
    if not isinstance(event_id, str) or len(event_id) > 64 or not isinstance(event_type, str) or len(event_type) > 64:
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

    should_queue = event_type == "settlement.processed" and bool(settlement)
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
