"""Unit tests for Bank Ingestion Service."""

import io

import pytest
from fastapi import HTTPException, UploadFile
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.main import app
from app.repositories.bank_repo import BankRepository
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

    mappings_json = json.dumps(
        {
            "date": "Value Date",
            "narration": "Particulars",
            "ref": "Instrument Id",
            "amount": "Deposit",
        }
    )

    resp = await service.ingest_statement(file, batch_id="test_custom_batch", column_mappings=mappings_json)
    assert resp.total_rows_parsed == 1
    assert resp.inserted_count == 1


@pytest.mark.asyncio
async def test_ingestion_enforces_max_csv_rows_before_db_writes(db_session: AsyncSession, monkeypatch):
    monkeypatch.setattr(settings, "MAX_CSV_ROWS", 3)
    service = IngestionService(db_session)

    header = b"Bank Statement\nDate,Chq/Ref No.,Narration,Deposit Amt.,Withdrawal Amt.\n"
    ok_rows = b"".join(f"24/08/2026,CMS00000000010{i},CMS/10{i}/HDFC,1000.00,0.00\n".encode() for i in range(1, 4))
    ok_file = UploadFile(filename="ok_3.csv", file=io.BytesIO(header + ok_rows), headers={"content-type": "text/csv"})
    ok_resp = await service.ingest_csv(ok_file, batch_id="limit_ok_batch")
    assert ok_resp.total_rows_parsed == 3
    assert ok_resp.inserted_count == 3

    too_many_rows = ok_rows + b"24/08/2026,CMS000000000104,CMS/104/HDFC,1000.00,0.00\n"
    bad_file = UploadFile(
        filename="too_many_4.csv",
        file=io.BytesIO(header + too_many_rows),
        headers={"content-type": "text/csv"},
    )
    with pytest.raises(HTTPException) as exc_info:
        await service.ingest_csv(bad_file, batch_id="limit_reject_batch")

    assert exc_info.value.status_code == 413
    assert isinstance(exc_info.value.detail, dict)
    assert exc_info.value.detail["code"] == "CSV_ROW_LIMIT_EXCEEDED"
    assert exc_info.value.detail["details"] == {"max_rows": 3}
    assert await BankRepository(db_session).get_all_by_batch("limit_reject_batch") == []


@pytest.mark.asyncio
async def test_ingestion_streams_chunks_without_full_read_and_rejects_oversized_bytes(
    db_session: AsyncSession,
    monkeypatch,
):
    monkeypatch.setattr(settings, "MAX_CSV_UPLOAD_MB", 1)
    service = IngestionService(db_session)

    header = b"Date,Chq/Ref No.,Narration,Deposit Amt.,Withdrawal Amt.\n"
    row_bytes = b"24/08/2026,CMS002938491801,CMS/002938491801/HDFC/RAZORPAY,98200.00,0.00\n"
    oversized = header + row_bytes * ((1024 * 1024 // len(row_bytes)) + 50)
    upload = UploadFile(
        filename="oversized.csv",
        file=io.BytesIO(oversized),
        headers={"content-type": "text/csv"},
    )

    read_sizes: list[int] = []
    orig_read = upload.read

    async def tracked_read(size: int = -1) -> bytes:
        read_sizes.append(size)
        return await orig_read(size)

    monkeypatch.setattr(upload, "read", tracked_read)

    with pytest.raises(HTTPException) as exc_info:
        await service.ingest_csv(upload, batch_id="size_reject_batch")

    assert exc_info.value.status_code == 413
    assert all(sz > 0 and sz <= 64 * 1024 for sz in read_sizes)


@pytest.mark.asyncio
async def test_bank_upload_endpoint_returns_413_envelope_when_row_limit_exceeded(
    db_session: AsyncSession,
    monkeypatch,
):
    monkeypatch.setattr(settings, "MAX_CSV_ROWS", 2)
    csv_content = (
        b"Date,Chq/Ref No.,Narration,Deposit Amt.,Withdrawal Amt.\n"
        b"24/08/2026,CMS002938491801,CMS/002938491801/HDFC,100.00,0.00\n"
        b"24/08/2026,CMS002938491802,CMS/002938491802/HDFC,200.00,0.00\n"
        b"24/08/2026,CMS002938491803,CMS/002938491803/HDFC,300.00,0.00\n"
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/bank/upload",
            data={"batch_id": "endpoint_limit_batch"},
            files={"file": ("over_limit.csv", io.BytesIO(csv_content), "text/csv")},
        )

    assert resp.status_code == 413
    body = resp.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "CSV_ROW_LIMIT_EXCEEDED"
    assert body["error"]["details"] == {"max_rows": 2}
