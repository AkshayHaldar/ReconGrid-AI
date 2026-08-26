"""Bank transaction Pydantic schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class BankTransactionBase(BaseModel):
    date: datetime
    amount: Decimal = Field(..., decimal_places=2, max_digits=18)
    direction: Literal["CREDIT", "DEBIT"] = "CREDIT"
    utr: Optional[str] = None
    description: str = ""
    raw_csv_row: dict[str, Any] = Field(default_factory=dict)


class BankTransactionCreate(BankTransactionBase):
    batch_id: str = "default"
    row_hash: str


class BankTransactionResponse(BankTransactionBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    batch_id: str
    row_hash: str
    created_at: datetime


class BankUploadResponse(BaseModel):
    batch_id: str
    filename: str
    total_rows_parsed: int
    inserted_count: int
    duplicate_count: int
    reconciled_immediately: int
