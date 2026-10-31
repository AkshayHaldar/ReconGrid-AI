"""Reconciliation ledger & diagnostic schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ReconciliationStatusResponse(BaseModel):
    batch_id: str
    total_records: int
    matched_count: int
    suggested_count: int
    conflict_count: int
    exception_count: int
    pending_count: int = 0
    match_rate_percentage: float
    total_ingested_amount: Decimal = Field(..., decimal_places=2)
    total_reconciled_amount: Decimal = Field(..., decimal_places=2)
    total_exception_amount: Decimal = Field(..., decimal_places=2)
    total_pending_amount: Decimal = Field(default=Decimal("0.00"), decimal_places=2)
    total_credit_amount: Decimal = Field(default=Decimal("0.00"), decimal_places=2)
    total_debit_amount: Decimal = Field(default=Decimal("0.00"), decimal_places=2)
    net_ingested_amount: Decimal = Field(default=Decimal("0.00"), decimal_places=2)
    total_suggested_amount: Decimal = Field(default=Decimal("0.00"), decimal_places=2)
    total_conflict_amount: Decimal = Field(default=Decimal("0.00"), decimal_places=2)
    total_unresolved_variance: Decimal = Field(default=Decimal("0.00"), decimal_places=2)
    is_in_balance: bool = False
    last_reconciled_at: datetime | None = None

    @field_validator(
        "total_ingested_amount",
        "total_reconciled_amount",
        "total_exception_amount",
        "total_pending_amount",
        "total_credit_amount",
        "total_debit_amount",
        "net_ingested_amount",
        "total_suggested_amount",
        "total_conflict_amount",
        "total_unresolved_variance",
        mode="before",
    )
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
    bank_utr: str | None = None
    bank_description: str
    bank_amount: Decimal = Field(..., decimal_places=2)
    bank_direction: Literal["CREDIT", "DEBIT"] = "CREDIT"

    # Matched Settlement info
    rzp_settlement_db_id: str | None = None
    rzp_settlement_id: str | None = None
    rzp_amount: Decimal | None = Field(default=None, decimal_places=2)
    rzp_gross_amount: Decimal | None = Field(default=None, decimal_places=2)
    rzp_fees: Decimal | None = Field(default=None, decimal_places=2)
    rzp_tax: Decimal | None = Field(default=None, decimal_places=2)
    rzp_utr: str | None = None

    # Status & Tier
    match_status: Literal["MATCHED", "SUGGESTED", "CONFLICT", "EXCEPTION", "PENDING_SETTLEMENT_DATA"]
    match_tier: Literal["TIER_0", "TIER_1", "TIER_2", "TIER_3", "MANUAL"]
    confidence_score: float | None = None
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
        "PENDING_SETTLEMENT",
        "DATE_AMOUNT_FALLBACK",
        "FUZZY_MATCH",
    ]
    diagnostic_note: str
    matched_at: datetime
    human_action: str | None = None
    raw_csv_row: dict[str, Any] | None = None
    raw_rzp_payload: dict[str, Any] | None = None

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
    note: str | None = None


class ConflictResolveRequest(BaseModel):
    chosen_settlement_id: str
    note: str | None = None


class ScorecardExceptionItem(BaseModel):
    bank_transaction_id: str
    date: datetime
    amount: Decimal = Field(..., decimal_places=2)
    reason_code: str
    diagnostic_note: str
    utr: str | None = None
    description: str

    @field_validator("amount", mode="before")
    @classmethod
    def validate_no_float(cls, v: Any) -> Any:
        if isinstance(v, float):
            raise ValueError("Float values are strictly forbidden for monetary fields; use Decimal, str, or int.")
        return v


class ScorecardResponse(BaseModel):
    batch_id: str
    total_rows_processed: int
    processing_time_seconds: Decimal = Field(..., decimal_places=4)
    rows_per_second: Decimal = Field(..., decimal_places=2)

    # Per-tier breakdown (Tier 0/1/2/3 kept separate)
    tier_0_count: int
    tier_0_percentage: Decimal = Field(..., decimal_places=2)
    tier_1_count: int
    tier_1_percentage: Decimal = Field(..., decimal_places=2)
    tier_2_count: int
    tier_2_percentage: Decimal = Field(..., decimal_places=2)
    tier_3_count: int
    tier_3_percentage: Decimal = Field(..., decimal_places=2)

    # Aggregate match statuses
    total_matched_count: int
    total_matched_percentage: Decimal = Field(..., decimal_places=2)
    total_suggested_count: int
    total_suggested_percentage: Decimal = Field(..., decimal_places=2)
    total_conflict_count: int
    total_conflict_percentage: Decimal = Field(..., decimal_places=2)
    total_exception_count: int
    total_exception_percentage: Decimal = Field(..., decimal_places=2)
    total_pending_count: int = 0
    total_pending_percentage: Decimal = Field(default=Decimal("0.00"), decimal_places=2)

    # Financial totals
    total_reconciled_amount: Decimal = Field(..., decimal_places=2)
    total_ingested_amount: Decimal = Field(..., decimal_places=2)
    total_exception_amount: Decimal = Field(..., decimal_places=2)
    total_pending_amount: Decimal = Field(default=Decimal("0.00"), decimal_places=2)
    total_credit_amount: Decimal = Field(default=Decimal("0.00"), decimal_places=2)
    total_debit_amount: Decimal = Field(default=Decimal("0.00"), decimal_places=2)
    net_ingested_amount: Decimal = Field(default=Decimal("0.00"), decimal_places=2)
    total_suggested_amount: Decimal = Field(default=Decimal("0.00"), decimal_places=2)
    total_conflict_amount: Decimal = Field(default=Decimal("0.00"), decimal_places=2)
    total_unresolved_variance: Decimal = Field(default=Decimal("0.00"), decimal_places=2)
    is_in_balance: bool = False

    # Conservation audit
    records_accounted_for: int
    unaccounted_records: int
    is_fully_accounted: bool

    # Full unfiltered exception array
    exceptions: list[ScorecardExceptionItem]

    @field_validator(
        "processing_time_seconds",
        "rows_per_second",
        "tier_0_percentage",
        "tier_1_percentage",
        "tier_2_percentage",
        "tier_3_percentage",
        "total_matched_percentage",
        "total_suggested_percentage",
        "total_conflict_percentage",
        "total_exception_percentage",
        "total_pending_percentage",
        "total_reconciled_amount",
        "total_ingested_amount",
        "total_exception_amount",
        "total_pending_amount",
        "total_credit_amount",
        "total_debit_amount",
        "net_ingested_amount",
        "total_suggested_amount",
        "total_conflict_amount",
        "total_unresolved_variance",
        mode="before",
    )
    @classmethod
    def validate_no_float(cls, v: Any) -> Any:
        if isinstance(v, float):
            raise ValueError("Float values are strictly forbidden for numeric fields; use Decimal, str, or int.")
        return v
