"""Bank statement CSV and PDF ingestion service with password decryption and OCR support."""

import io
import json
import tempfile
from collections.abc import Iterator
from typing import Any

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.repositories.bank_repo import BankRepository
from app.repositories.reconciliation_repo import ReconciliationRepository
from app.repositories.settlement_repo import SettlementRepository
from app.schemas.bank import BankUploadResponse
from app.services.reconciliation import ReconciliationEngine
from app.utils.csv_parser import BankCsvParser, CsvRowLimitExceededError
from app.utils.pdf_parser import (
    BANK_PASSWORD_FORMATS,
    BankPdfParser,
    PdfInvalidPasswordError,
    PdfPasswordRequiredError,
)

_UPLOAD_CHUNK_BYTES = 64 * 1024
_CSV_SPOOL_MEMORY_BYTES = 1024 * 1024


def _parse_column_mappings(column_mappings: str | dict[str, Any] | None) -> dict[str, str] | None:
    """Normalize optional JSON-encoded or dict column mappings."""
    if not column_mappings:
        return None
    if isinstance(column_mappings, str):
        try:
            loaded = json.loads(column_mappings)
        except Exception as ex:
            logger.warning("invalid_column_mappings_json", error=str(ex))
            return None
        if not isinstance(loaded, dict):
            return None
        return {str(k).strip(): str(v).strip() for k, v in loaded.items() if v is not None and str(v).strip() != ""}
    if isinstance(column_mappings, dict):
        return {
            str(k).strip(): str(v).strip() for k, v in column_mappings.items() if v is not None and str(v).strip() != ""
        }
    return None


_HTTP_413_STATUS: int = getattr(status, "HTTP_413_CONTENT_TOO_LARGE", 413)


def _raise_file_too_large() -> None:
    raise HTTPException(
        status_code=_HTTP_413_STATUS,
        detail=f"File exceeds maximum allowed size of {settings.MAX_CSV_UPLOAD_MB} MB.",
    )


def _raise_row_limit_exceeded(max_rows: int) -> None:
    raise HTTPException(
        status_code=_HTTP_413_STATUS,
        detail={
            "code": "CSV_ROW_LIMIT_EXCEEDED",
            "message": f"CSV exceeds maximum allowed limit of {max_rows} rows.",
            "details": {"max_rows": max_rows},
        },
    )


async def _read_bounded_bytes(file: UploadFile, max_bytes: int) -> bytes:
    """Read binary upload content in chunks while enforcing max_bytes."""
    buf = bytearray()
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > max_bytes:
            _raise_file_too_large()
    return bytes(buf)


async def _spool_csv_upload(file: UploadFile, max_bytes: int) -> tempfile.SpooledTemporaryFile[bytes]:
    """Stream CSV upload into a SpooledTemporaryFile in bounded chunks without full-RAM buffering."""
    spooled: tempfile.SpooledTemporaryFile[bytes] = tempfile.SpooledTemporaryFile(
        max_size=_CSV_SPOOL_MEMORY_BYTES,
        mode="w+b",
    )
    total_bytes = 0
    try:
        while True:
            chunk = await file.read(_UPLOAD_CHUNK_BYTES)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                _raise_file_too_large()
            spooled.write(chunk)
        spooled.seek(0)
        return spooled
    except Exception:
        spooled.close()
        raise


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
        password: str | None = None,
        column_mappings: str | dict | None = None,
    ) -> BankUploadResponse:
        """Parses bank statement (CSV or PDF), records transactions, and runs reconciliation."""
        filename = file.filename or "statement.csv"
        ext = filename.lower().split(".")[-1] if "." in filename else ""

        # Validate file type with generous browser & OS MIME type fallback
        content_type = (file.content_type or "").lower().strip()
        valid_csv = ext in {"csv", "txt"} or content_type in {
            "text/csv",
            "application/vnd.ms-excel",
            "text/plain",
            "application/octet-stream",
            "text/comma-separated-values",
            "application/csv",
            "text/x-csv",
        }
        valid_pdf = ext == "pdf" or content_type in {
            "application/pdf",
            "application/x-pdf",
            "application/acrobat",
            "applications/vnd.pdf",
            "text/pdf",
            "text/x-pdf",
        }

        if not (valid_csv or valid_pdf):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type for '{filename}'. Only CSV and PDF bank statements are supported.",
            )

        max_bytes = settings.MAX_CSV_UPLOAD_MB * 1024 * 1024

        if valid_pdf:
            contents = await _read_bounded_bytes(file, max_bytes=max_bytes)
            try:
                pdf_rows = BankPdfParser.parse_pdf(contents, password=password)
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
                    detail=f"Failed to parse bank statement PDF: {ex!s}",
                )

            (
                parsed_rows_count,
                inserted_count,
                duplicate_count,
                valid_rows_count,
                validation_errors,
                all_batch_txs,
            ) = await self._consume_parsed_rows(iter(pdf_rows), batch_id=batch_id)
        else:
            parsed_mappings = _parse_column_mappings(column_mappings)
            max_rows = max(0, settings.MAX_CSV_ROWS)
            spooled = await _spool_csv_upload(file, max_bytes=max_bytes)
            try:
                # Enforce row count limit before database writes begin.
                precheck_stream = io.TextIOWrapper(spooled, encoding="utf-8-sig", errors="replace", newline="")
                try:
                    BankCsvParser.count_data_rows(
                        precheck_stream,
                        custom_mappings=parsed_mappings,
                        max_rows=max_rows,
                    )
                except CsvRowLimitExceededError:
                    _raise_row_limit_exceeded(max_rows)
                finally:
                    precheck_stream.detach()

                spooled.seek(0)
                parse_stream = io.TextIOWrapper(spooled, encoding="utf-8-sig", errors="replace", newline="")
                try:
                    row_iter = BankCsvParser.parse_csv_stream(
                        parse_stream,
                        custom_mappings=parsed_mappings,
                        max_rows=max_rows,
                    )
                    (
                        parsed_rows_count,
                        inserted_count,
                        duplicate_count,
                        valid_rows_count,
                        validation_errors,
                        all_batch_txs,
                    ) = await self._consume_parsed_rows(row_iter, batch_id=batch_id)
                except CsvRowLimitExceededError:
                    _raise_row_limit_exceeded(max_rows)
                finally:
                    parse_stream.detach()
            finally:
                spooled.close()

        if parsed_rows_count == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid bank transaction rows could be parsed from the uploaded file.",
            )

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
            parsed_rows=parsed_rows_count,
            inserted=inserted_count,
            duplicates=duplicate_count,
            validation_errors=len(validation_errors),
            reconciled=len(reconciled_logs),
        )

        return BankUploadResponse(
            batch_id=batch_id,
            filename=filename,
            total_rows_parsed=parsed_rows_count,
            inserted_count=inserted_count,
            duplicate_count=duplicate_count,
            reconciled_immediately=len(reconciled_logs),
            validation_errors=validation_errors,
        )

    async def _consume_parsed_rows(
        self,
        row_iter: Iterator[dict[str, Any]],
        batch_id: str,
    ) -> tuple[int, int, int, int, list[str], list[Any]]:
        """Stream parsed rows into repository upserts without materializing a full list."""
        parsed_rows_count = 0
        inserted_count = 0
        duplicate_count = 0
        valid_rows_count = 0
        validation_errors: list[str] = []
        all_batch_txs: list[Any] = []

        for row in row_iter:
            parsed_rows_count += 1
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

        return (
            parsed_rows_count,
            inserted_count,
            duplicate_count,
            valid_rows_count,
            validation_errors,
            all_batch_txs,
        )

    # Maintain backward compatibility for any direct call
    async def ingest_csv(
        self,
        file: UploadFile,
        batch_id: str = "default",
        column_mappings: str | dict | None = None,
    ) -> BankUploadResponse:
        return await self.ingest_statement(file, batch_id=batch_id, column_mappings=column_mappings)
