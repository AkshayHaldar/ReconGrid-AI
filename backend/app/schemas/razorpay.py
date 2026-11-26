"""Razorpay settlement schemas."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.money import paise_to_rupees


class RazorpayRefundPayload(BaseModel):
    """Refund entity shared by the paginated provider API and signed webhooks."""

    id: str = Field(min_length=1, max_length=64)
    payment_id: str = Field(min_length=1, max_length=64)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount: int = Field(strict=True, gt=0, lt=10**18)
    status: Literal["pending", "processed", "failed"]
    created_at: int = Field(strict=True, gt=0)

    @field_validator("created_at")
    @classmethod
    def validate_timestamp(cls, value: int) -> int:
        try:
            datetime.fromtimestamp(value, UTC)
        except (OverflowError, OSError, ValueError) as error:
            raise ValueError("Refund timestamp is out of range") from error
        return value

    def to_record(self, raw_payload: dict[str, Any]) -> dict[str, Any]:
        if self.currency != "INR":
            raise ValueError("ReconGrid stores only INR refund amounts")
        return {
            "refund_id": self.id,
            "payment_id": self.payment_id,
            "amount": paise_to_rupees(self.amount),
            "status": self.status,
            # The refund entity exposes its creation time, including in processed deliveries.
            "processed_at": datetime.fromtimestamp(self.created_at, UTC),
            "raw_payload": raw_payload,
        }


class RazorpaySettlementBase(BaseModel):
    settlement_id: str
    amount: Decimal = Field(..., decimal_places=2, max_digits=18)
    gross_amount: Decimal = Field(default=Decimal("0.00"), decimal_places=2, max_digits=18)
    fees: Decimal = Field(default=Decimal("0.00"), decimal_places=2, max_digits=18)
    tax: Decimal = Field(default=Decimal("0.00"), decimal_places=2, max_digits=18)
    utr: str | None = None
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
