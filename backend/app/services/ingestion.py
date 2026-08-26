"""Bank statement CSV ingestion service."""

import io
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


class IngestionService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.bank_repo = BankRepository(session)
        self.settlement_repo = SettlementRepository(session)
        self.recon_repo = ReconciliationRepository(session)
        self.engine = ReconciliationEngine(self.recon_repo)

    async def ingest_csv(
        self,
        file: UploadFile,
        batch_id: str = "default",
    ) -> BankUploadResponse:
        """Streams and parses bank statement CSV, records transactions, and runs reconciliation."""
        filename = file.filename or "statement.csv"

        # Validate file type
        if not (filename.lower().endswith(".csv") or file.content_type in {"text/csv", "application/vnd.ms-excel", "text/plain"}):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type for {filename}. Only CSV bank statements are supported.",
            )

        # Read contents with streaming safeguard
        max_bytes = settings.MAX_CSV_UPLOAD_MB * 1024 * 1024
        contents = await file.read(max_bytes + 1)
        if len(contents) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds maximum allowed size of {settings.MAX_CSV_UPLOAD_MB} MB.",
            )

        try:
            text_data = contents.decode("utf-8-sig", errors="replace")
        except Exception:
            text_data = contents.decode("latin-1", errors="replace")

        lines = text_data.splitlines()
        parsed_rows = list(BankCsvParser.parse_csv_stream(iter(lines)))

        if not parsed_rows:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid bank transaction rows could be parsed from the uploaded CSV.",
            )

        inserted_count = 0
        duplicate_count = 0
        all_batch_txs = []

        for row in parsed_rows:
            row["batch_id"] = batch_id
            tx, created = await self.bank_repo.upsert_transaction(row)
            all_batch_txs.append(tx)
            if created:
                inserted_count += 1
            else:
                duplicate_count += 1

        # Fetch available settlements to run deterministic reconciliation
        settlements = await self.settlement_repo.get_all()

        # Run reconciliation pipeline
        reconciled_logs = await self.engine.reconcile_batch(
            bank_transactions=all_batch_txs,
            settlements=settlements,
            batch_id=batch_id,
        )

        logger.info(
            "bank_csv_ingestion_completed",
            filename=filename,
            parsed_rows=len(parsed_rows),
            inserted=inserted_count,
            duplicates=duplicate_count,
            reconciled=len(reconciled_logs),
        )

        return BankUploadResponse(
            batch_id=batch_id,
            filename=filename,
            total_rows_parsed=len(parsed_rows),
            inserted_count=inserted_count,
            duplicate_count=duplicate_count,
            reconciled_immediately=len(reconciled_logs),
        )
