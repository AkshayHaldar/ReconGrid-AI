"""Bank statement CSV and PDF ingestion service with password decryption and OCR support."""

import io
from typing import Optional
from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.repositories.bank_repo import BankRepository
from app.repositories.reconciliation_repo import ReconciliationRepository
from app.repositories.settlement_repo import SettlementRepository
from app.schemas.bank import BankUploadResponse
from app.services.reconciliation import ReconciliationEngine
from app.utils.csv_parser import BankCsvParser
from app.utils.pdf_parser import (
    BANK_PASSWORD_FORMATS,
    BankPdfParser,
    PdfInvalidPasswordError,
    PdfPasswordRequiredError,
)


class IngestionService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.bank_repo = BankRepository(session)
        self.settlement_repo = SettlementRepository(session)
        self.recon_repo = ReconciliationRepository(session)
        self.engine = ReconciliationEngine(self.recon_repo)

    async def ingest_statement(
        self,
        file: UploadFile,
        batch_id: str = "default",
        password: Optional[str] = None,
    ) -> BankUploadResponse:
        """Parses bank statement (CSV or PDF), records transactions, and runs reconciliation."""
        filename = file.filename or "statement.csv"
        ext = filename.lower().split(".")[-1] if "." in filename else ""

        # Validate file type with generous browser & OS MIME type fallback
        content_type = (file.content_type or "").lower().strip()
        valid_csv = (
            ext in {"csv", "txt"}
            or content_type in {
                "text/csv",
                "application/vnd.ms-excel",
                "text/plain",
                "application/octet-stream",
                "text/comma-separated-values",
                "application/csv",
                "text/x-csv",
            }
        )
        valid_pdf = (
            ext == "pdf"
            or content_type in {
                "application/pdf",
                "application/x-pdf",
                "application/acrobat",
                "applications/vnd.pdf",
                "text/pdf",
                "text/x-pdf",
            }
        )

        if not (valid_csv or valid_pdf):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type for '{filename}'. Only CSV and PDF bank statements are supported.",
            )

        # Read contents with streaming size safeguard
        max_bytes = settings.MAX_CSV_UPLOAD_MB * 1024 * 1024
        contents = await file.read(max_bytes + 1)
        if len(contents) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds maximum allowed size of {settings.MAX_CSV_UPLOAD_MB} MB.",
            )

        parsed_rows = []

        if valid_pdf:
            try:
                parsed_rows = BankPdfParser.parse_pdf(contents, password=password)
            except PdfPasswordRequiredError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "PASSWORD_REQUIRED",
                        "message": "This bank statement PDF is password-protected. Please enter your PDF password.",
                        "hints": BANK_PASSWORD_FORMATS,
                    },
                )
            except PdfInvalidPasswordError as ex:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "INVALID_PASSWORD",
                        "message": str(ex),
                        "hints": BANK_PASSWORD_FORMATS,
                    },
                )
            except Exception as ex:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to parse bank statement PDF: {str(ex)}",
                )
        else:
            # Parse CSV
            try:
                text_data = contents.decode("utf-8-sig", errors="replace")
            except Exception:
                text_data = contents.decode("latin-1", errors="replace")

            lines = text_data.splitlines()
            parsed_rows = list(BankCsvParser.parse_csv_stream(iter(lines)))

        if not parsed_rows:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid bank transaction rows could be parsed from the uploaded file.",
            )

        inserted_count = 0
        duplicate_count = 0
        all_batch_txs = []
        validation_errors: list[str] = []
        valid_rows_count = 0

        for row in parsed_rows:
            if "validation_error" in row:
                validation_errors.append(row["validation_error"])
                continue
            valid_rows_count += 1
            row["batch_id"] = batch_id
            tx, created = await self.bank_repo.upsert_transaction(row)
            all_batch_txs.append(tx)
            if created:
                inserted_count += 1
            else:
                duplicate_count += 1

        if valid_rows_count == 0 and validation_errors:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "STATEMENT_VALIDATION_ERROR",
                    "message": "All transaction rows in uploaded statement failed validation.",
                    "errors": validation_errors,
                },
            )

        # Fetch available settlements to run deterministic reconciliation
        settlements = await self.settlement_repo.get_all()

        # Run reconciliation pipeline
        reconciled_logs = await self.engine.reconcile_batch(
            bank_transactions=all_batch_txs,
            settlements=settlements,
            batch_id=batch_id,
        )

        logger.info(
            "bank_statement_ingestion_completed",
            filename=filename,
            file_type="pdf" if valid_pdf else "csv",
            parsed_rows=len(parsed_rows),
            inserted=inserted_count,
            duplicates=duplicate_count,
            validation_errors=len(validation_errors),
            reconciled=len(reconciled_logs),
        )

        return BankUploadResponse(
            batch_id=batch_id,
            filename=filename,
            total_rows_parsed=len(parsed_rows),
            inserted_count=inserted_count,
            duplicate_count=duplicate_count,
            reconciled_immediately=len(reconciled_logs),
            validation_errors=validation_errors,
        )

    # Maintain backward compatibility for any direct call
    async def ingest_csv(self, file: UploadFile, batch_id: str = "default") -> BankUploadResponse:
        return await self.ingest_statement(file, batch_id=batch_id)
