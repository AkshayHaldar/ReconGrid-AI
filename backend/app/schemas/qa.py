"""Settlement Q&A Agent schemas."""

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict


class QaAskRequest(BaseModel):
    query: str


class QaAskResponse(BaseModel):
    query: str
    answer: str
    source_record_id: Optional[str] = None
    source_settlement_id: Optional[str] = None
    source_bank_utr: Optional[str] = None
    guardrail_rejected: bool = False
    retrieved_data: Optional[dict[str, Any]] = None
    asked_at: datetime


class QaHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    query_text: str
    final_response: str
    reconciliation_log_id: Optional[str] = None
    guardrail_rejected: bool
    asked_at: datetime
