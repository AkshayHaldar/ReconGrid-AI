"""Unit tests for Bank Ingestion Service."""

import io

import pytest
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ingestion import IngestionService


@pytest.mark.asyncio
async def test_ingestion_service_hdfc_csv(db_session: AsyncSession):
    service = IngestionService(db_session)

    csv_content = (
        b"Date,Chq/Ref No.,Narration,Deposit Amt.,Withdrawal Amt.\n"
        b"24/08/2026,CMS002938491801,CMS/002938491801/HDFC/RAZORPAY,98200.00,0.00\n"
        b"24/08/2026,CMS002938491802,CMS/002938491802/HDFC/RAZORPAY,45000.00,0.00\n"
    )

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


@pytest.mark.asyncio
async def test_ingestion_service_custom_column_mappings_json(db_session: AsyncSession):
    import json

    service = IngestionService(db_session)

    csv_content = (
        b"Federal Bank Corporate Statement\n"
        b"Account 9876543210\n"
        b"\n"
        b"Value Date,Particulars,Instrument Id,Deposit,Withdrawal,Balance\n"
        b"24-08-2026,RAZORPAY SETTLEMENT BANGALORE,CMS002938491899,92500.00,0.00,192500.00\n"
    )

    file = UploadFile(
        filename="federal_custom_statement.csv",
        file=io.BytesIO(csv_content),
        headers={"content-type": "text/csv"},
    )

    mappings_json = json.dumps({
        "date": "Value Date",
        "narration": "Particulars",
        "ref": "Instrument Id",
        "amount": "Deposit",
    })

    resp = await service.ingest_statement(file, batch_id="test_custom_batch", column_mappings=mappings_json)
    assert resp.total_rows_parsed == 1
    assert resp.inserted_count == 1
