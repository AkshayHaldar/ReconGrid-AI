"""Unit tests for Bank Ingestion Service."""

import io
from decimal import Decimal
from fastapi import UploadFile
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.ingestion import IngestionService


@pytest.mark.asyncio
async def test_ingestion_service_hdfc_csv(db_session: AsyncSession):
    service = IngestionService(db_session)

    csv_content = (
        "Date,Chq/Ref No.,Narration,Deposit Amt.,Withdrawal Amt.\n"
        "24/08/2026,CMS002938491801,CMS/002938491801/HDFC/RAZORPAY,98200.00,0.00\n"
        "24/08/2026,CMS002938491802,CMS/002938491802/HDFC/RAZORPAY,45000.00,0.00\n"
    ).encode("utf-8")

    file = UploadFile(
        filename="hdfc_statement.csv",
        file=io.BytesIO(csv_content),
        headers={"content-type": "text/csv"},
    )

    resp = await service.ingest_csv(file, batch_id="test_ingest_batch")
    assert resp.total_rows_parsed == 2
    assert resp.inserted_count == 2
    assert resp.duplicate_count == 0

    # Re-upload same file to verify idempotency (0 new inserts, 2 duplicates)
    file2 = UploadFile(
        filename="hdfc_statement.csv",
        file=io.BytesIO(csv_content),
        headers={"content-type": "text/csv"},
    )
    resp2 = await service.ingest_csv(file2, batch_id="test_ingest_batch")
    assert resp2.total_rows_parsed == 2
    assert resp2.inserted_count == 0
    assert resp2.duplicate_count == 2
