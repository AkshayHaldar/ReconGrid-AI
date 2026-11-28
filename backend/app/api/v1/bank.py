"""Bank Statement API Routes."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.repositories.bank_repo import BankRepository
from app.schemas.bank import BankTransactionResponse, BankUploadResponse
from app.schemas.common import ApiResponse
from app.services.ingestion import IngestionService
from app.utils.pdf_parser import BANK_PASSWORD_FORMATS

router = APIRouter(prefix="/bank", tags=["Bank Transactions"])

ALLOWED_EXTENSIONS = (".csv", ".pdf", ".xls", ".xlsx")
_SIZE_CHECK_CHUNK_BYTES = 1024 * 1024


async def validate_statement_upload(file: UploadFile) -> None:
    """Rejects unsupported or oversized uploads before the statement is loaded for parsing."""
    if not (file.filename or "").lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                "Unsupported file type. Please upload a bank statement in one of these formats: "
                f"{', '.join(ALLOWED_EXTENSIONS)}."
            ),
        )

    max_bytes = settings.MAX_CSV_UPLOAD_MB * 1024 * 1024
    size = file.size
    if size is None:
        # Count in chunks so memory use stays flat, then rewind for the parser.
        size = 0
        while size <= max_bytes and (chunk := await file.read(_SIZE_CHECK_CHUNK_BYTES)):
            size += len(chunk)
        await file.seek(0)

    if size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"File size exceeds the {settings.MAX_CSV_UPLOAD_MB} MB limit. "
                "Please split the statement or contact support."
            ),
        )


@router.post("/upload", response_model=ApiResponse[BankUploadResponse])
async def upload_bank_statement(
    file: UploadFile = File(...),
    batch_id: str = Form(default="default"),
    password: str | None = Form(default=None),
    column_mappings: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Uploads and parses a bank statement (CSV or password-protected PDF)."""
    await validate_statement_upload(file)
    service = IngestionService(db)
    result = await service.ingest_statement(file, batch_id=batch_id, password=password, column_mappings=column_mappings)
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
