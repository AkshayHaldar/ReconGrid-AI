"""Webhook payload schemas."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class RazorpayWebhookPayload(BaseModel):
    entity: str = "event"
    account_id: str = ""
    event: str
    contains: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: int = 0


class WebhookAckResponse(BaseModel):
    status: str = "ok"
    event_id: str | None = None
    action_taken: str


class WebhookEventItem(BaseModel):
    """One row of the gateway activity feed."""

    event_id: str
    event_type: str
    received_at: datetime
    settlement_id: str | None = None
    utr: str | None = None
    signature_status: Literal["VALID", "INVALID", "MALFORMED"]
    ingestion_status: Literal["RECONCILIATION_TRIGGERED", "IGNORED", "FAILED", "REJECTED"]
    processing_status: str
    payload: dict[str, Any] = Field(default_factory=dict)


class WebhookHealth(BaseModel):
    """Heartbeat summary used by the header pulse indicator."""

    status: Literal["live", "idle", "warning"]
    last_verified_at: datetime | None = None
    last_rejected_at: datetime | None = None
    last_rejection_reason: Literal["INVALID_SIGNATURE", "MALFORMED_PAYLOAD"] | None = None
    message: str
