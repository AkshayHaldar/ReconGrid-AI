"""Razorpay Webhook receiver API Route."""

import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
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


@router.post("/razorpay", response_model=ApiResponse[WebhookAckResponse])
async def handle_razorpay_webhook(
    request: Request,
    raw_body: bytes = Depends(razorpay_webhook_guard),
    db: AsyncSession = Depends(get_db),
):
    """HMAC-verified, idempotent Razorpay webhook consumer."""
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON webhook body")

    event_id = payload.get("id") or payload.get("event_id") or f"evt_{hash(raw_body)}"
    event_type = payload.get("event", "unknown")

    # 1. Deduplication check on event_id
    stmt = select(ProcessedWebhookEvent).where(ProcessedWebhookEvent.razorpay_event_id == event_id)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        logger.info("duplicate_webhook_ignored", event_id=event_id, event_type=event_type)
        return ApiResponse.ok(
            WebhookAckResponse(status="ok", event_id=event_id, action_taken="DUPLICATE_IGNORED")
        )

    # 2. Record processed webhook event
    event_record = ProcessedWebhookEvent(
        razorpay_event_id=event_id,
        event_type=event_type,
        processing_status="PROCESSED",
        payload=payload,
        received_at=datetime.now(timezone.utc),
    )
    db.add(event_record)
    await db.flush()

    # 3. Process settlement.processed event
    if event_type == "settlement.processed":
        setl_data = payload.get("payload", {}).get("settlement", {}).get("entity", {})
        if setl_data:
            amount_inr = paise_to_rupees(setl_data.get("amount", 0))
            fees_inr = paise_to_rupees(setl_data.get("fees", 0))
            tax_inr = paise_to_rupees(setl_data.get("tax", 0))
            gross_inr = amount_inr + fees_inr + tax_inr

            created_ts = setl_data.get("created_at")
            dt = (
                datetime.fromtimestamp(created_ts, timezone.utc)
                if created_ts
                else datetime.now(timezone.utc)
            )

            settlement_repo = SettlementRepository(db)
            setl_obj, _ = await settlement_repo.upsert_settlement({
                "settlement_id": setl_data.get("id", f"setl_{event_id}"),
                "amount": amount_inr,
                "gross_amount": gross_inr,
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

            bank_txs = await bank_repo.get_all_by_batch("default")
            all_setls = await settlement_repo.get_all()
            if bank_txs:
                await engine.reconcile_batch(bank_txs, all_setls, batch_id="default")

    return ApiResponse.ok(
        WebhookAckResponse(status="ok", event_id=event_id, action_taken="PROCESSED_AND_RECONCILED")
    )
