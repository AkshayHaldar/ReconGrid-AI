"""Bank Statement API Routes."""

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.repositories.bank_repo import BankRepository
from app.schemas.bank import BankTransactionResponse, BankUploadResponse
from app.schemas.common import ApiResponse
from app.services.ingestion import IngestionService

from typing import Optional
from app.utils.pdf_parser import BANK_PASSWORD_FORMATS

router = APIRouter(prefix="/bank", tags=["Bank Transactions"])


@router.post("/upload", response_model=ApiResponse[BankUploadResponse])
async def upload_bank_statement(
    file: UploadFile = File(...),
    batch_id: str = Form(default="default"),
    password: Optional[str] = Form(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Uploads and parses a bank statement (CSV or password-protected PDF)."""
    service = IngestionService(db)
    result = await service.ingest_statement(file, batch_id=batch_id, password=password)
    return ApiResponse.ok(result)


@router.get("/password-hints", response_model=ApiResponse[list[dict]])
async def get_bank_password_hints():
    """Returns password generation patterns/logic for major Indian banks."""
    return ApiResponse.ok(BANK_PASSWORD_FORMATS)


@router.get("/transactions", response_model=ApiResponse[list[BankTransactionResponse]])
async def list_bank_transactions(
    batch_id: str = "default",
    db: AsyncSession = Depends(get_db),
):
    """Lists all parsed bank transactions for a batch."""
    repo = BankRepository(db)
    txs = await repo.get_all_by_batch(batch_id)
    items = [BankTransactionResponse.model_validate(t) for t in txs]
    return ApiResponse.ok(items)
