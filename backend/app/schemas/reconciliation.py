"""Reconciliation ledger & diagnostic schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReconciliationStatusResponse(BaseModel):
    batch_id: str
    total_records: int
    matched_count: int
    suggested_count: int
    conflict_count: int
    exception_count: int
    match_rate_percentage: float
    total_ingested_amount: Decimal = Field(..., decimal_places=2)
    total_reconciled_amount: Decimal = Field(..., decimal_places=2)
    total_exception_amount: Decimal = Field(..., decimal_places=2)
    last_reconciled_at: Optional[datetime] = None

    @field_validator("total_ingested_amount", "total_reconciled_amount", "total_exception_amount", mode="before")
    @classmethod
    def validate_no_float(cls, v: Any) -> Any:
        if isinstance(v, float):
            raise ValueError("Float values are strictly forbidden for monetary fields; use Decimal, str, or int.")
        return v


class ReconciliationRecordItem(BaseModel):
    id: str
    batch_id: str
    bank_tx_id: str
    date: datetime
    bank_utr: Optional[str] = None
    bank_description: str
    bank_amount: Decimal = Field(..., decimal_places=2)
    bank_direction: Literal["CREDIT", "DEBIT"] = "CREDIT"

    # Matched Settlement info
    rzp_settlement_db_id: Optional[str] = None
    rzp_settlement_id: Optional[str] = None
    rzp_amount: Optional[Decimal] = Field(default=None, decimal_places=2)
    rzp_gross_amount: Optional[Decimal] = Field(default=None, decimal_places=2)
    rzp_fees: Optional[Decimal] = Field(default=None, decimal_places=2)
    rzp_tax: Optional[Decimal] = Field(default=None, decimal_places=2)
    rzp_utr: Optional[str] = None

    # Status & Tier
    match_status: Literal["MATCHED", "SUGGESTED", "CONFLICT", "EXCEPTION"]
    match_tier: Literal["TIER_0", "TIER_1", "TIER_2", "TIER_3", "MANUAL"]
    confidence_score: Optional[float] = None
    delta_amount: Decimal = Field(default=Decimal("0.00"), decimal_places=2)
    diagnostic_type: Literal[
        "EXACT_MATCH",
        "FEE_DEDUCTION",
        "TDS_194O_DEDUCTION",
        "BATCHED_SETTLEMENT",
        "REFUND_ADJUSTED",
        "FX_ADJUSTED",
        "REVERSAL",
        "UNRESOLVED",
        "DATE_AMOUNT_FALLBACK",
        "FUZZY_MATCH",
    ]
    diagnostic_note: str
    matched_at: datetime
    human_action: Optional[str] = None
    raw_csv_row: Optional[dict[str, Any]] = None
    raw_rzp_payload: Optional[dict[str, Any]] = None

    @field_validator(
        "bank_amount",
        "rzp_amount",
        "rzp_gross_amount",
        "rzp_fees",
        "rzp_tax",
        "delta_amount",
        mode="before",
    )
    @classmethod
    def validate_no_float(cls, v: Any) -> Any:
        if isinstance(v, float):
            raise ValueError("Float values are strictly forbidden for monetary fields; use Decimal, str, or int.")
        return v


class ReconciliationRecordListResponse(BaseModel):
    batch_id: str
    records: list[ReconciliationRecordItem]
    total_count: int
    page: int
    page_size: int


class ActionRequest(BaseModel):
    note: Optional[str] = None


class ConflictResolveRequest(BaseModel):
    chosen_settlement_id: str
    note: Optional[str] = None
