"""Razorpay settlement schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class RazorpaySettlementBase(BaseModel):
    settlement_id: str
    amount: Decimal = Field(..., decimal_places=2, max_digits=18)
    gross_amount: Decimal = Field(default=Decimal("0.00"), decimal_places=2, max_digits=18)
    fees: Decimal = Field(default=Decimal("0.00"), decimal_places=2, max_digits=18)
    tax: Decimal = Field(default=Decimal("0.00"), decimal_places=2, max_digits=18)
    utr: Optional[str] = None
    status: str = "processed"
    settlement_created_at: datetime
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    is_test_mode: bool = True

    @field_validator("amount", "gross_amount", "fees", "tax", mode="before")
    @classmethod
    def validate_no_float(cls, v: Any) -> Any:
        if isinstance(v, float):
            raise ValueError("Float values are strictly forbidden for monetary fields; use Decimal, str, or int.")
        return v


class RazorpaySettlementCreate(RazorpaySettlementBase):
    pass


class RazorpaySettlementResponse(RazorpaySettlementBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


class RazorpaySyncRequest(BaseModel):
    count: int = Field(default=100, ge=1, le=100)
    skip: int = Field(default=0, ge=0)
    force_resync: bool = False


class RazorpaySyncResponse(BaseModel):
    fetched_count: int
    newly_inserted: int
    updated_count: int
    reconciliation_triggered: bool
