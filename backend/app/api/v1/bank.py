"""Bank Statement API Routes."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.bank_repo import BankRepository
from app.schemas.bank import BankTransactionResponse, BankUploadResponse
from app.schemas.common import ApiResponse
from app.services.ingestion import IngestionService
from app.utils.pdf_parser import BANK_PASSWORD_FORMATS

router = APIRouter(prefix="/bank", tags=["Bank Transactions"])

ALLOWED_EXTENSIONS = {".csv", ".pdf", ".xls", ".xlsx"}
MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB
CHUNK_SIZE = 1024 * 1024  # 1 MB


async def validate_upload_file(file: UploadFile, request: Request | None = None) -> None:
    """Validates file extension and size constraints for bank statements."""
    filename = file.filename or ""
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{ext or 'unknown'}'. Only .csv, .pdf, .xls, and .xlsx files are accepted.",
        )

    if file.size is not None and file.size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds the 15 MB limit. Please split the statement or contact support.",
        )

    content_length = file.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_FILE_SIZE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="File size exceeds the 15 MB limit. Please split the statement or contact support.",
                )
        except ValueError:
            pass

    if request is not None:
        req_content_length = request.headers.get("content-length")
        if req_content_length:
            try:
                if int(req_content_length) > MAX_FILE_SIZE_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="File size exceeds the 15 MB limit. Please split the statement or contact support.",
                    )
            except ValueError:
                pass

    total_size = 0
    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > MAX_FILE_SIZE_BYTES:
            await file.seek(0)
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File size exceeds the 15 MB limit. Please split the statement or contact support.",
            )

    await file.seek(0)


@router.post("/upload", response_model=ApiResponse[BankUploadResponse])
async def upload_bank_statement(
    request: Request,
    file: UploadFile = File(...),
    batch_id: str = Form(default="default"),
    password: str | None = Form(default=None),
    column_mappings: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Uploads and parses a bank statement (CSV or password-protected PDF)."""
    await validate_upload_file(file, request=request)
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
