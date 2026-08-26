"""Webhook payload schemas."""

from typing import Any, Optional
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
    event_id: Optional[str] = None
    action_taken: str
