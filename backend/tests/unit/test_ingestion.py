"""Unit tests for bank statement upload validation and ingestion limits."""

import io

import pytest
from fastapi import HTTPException, UploadFile, status

from app.api.v1.bank import validate_upload_file


@pytest.mark.asyncio
async def test_upload_file_rejected_invalid_extension():
    """Verify that uploading a file with an unsupported extension (e.g. .exe) raises HTTP 415."""
    file = UploadFile(
        filename="malicious.exe",
        file=io.BytesIO(b"MZ\x90\x00executable content"),
        headers={"content-type": "application/x-msdownload"},
    )

    with pytest.raises(HTTPException) as exc_info:
        await validate_upload_file(file)

    assert exc_info.value.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    assert "Only .csv, .pdf, .xls, and .xlsx files are accepted" in exc_info.value.detail


@pytest.mark.asyncio
async def test_upload_file_rejected_oversized():
    """Verify that uploading a file exceeding 15 MB raises HTTP 413 without loading into RAM."""
    sixteen_mb = 16 * 1024 * 1024

    class MockLargeStream(io.RawIOBase):
        def __init__(self, size: int):
            self.remaining = size

        def read(self, n=-1):
            if self.remaining <= 0:
                return b""
            chunk_size = min(n if n and n > 0 else self.remaining, self.remaining)
            self.remaining -= chunk_size
            return b"0" * chunk_size

        def seek(self, offset, whence=0):
            return 0

    mock_file = MockLargeStream(sixteen_mb)
    file = UploadFile(
        filename="large_statement.csv",
        file=mock_file,
        headers={"content-length": str(sixteen_mb), "content-type": "text/csv"},
    )

    with pytest.raises(HTTPException) as exc_info:
        await validate_upload_file(file)

    assert exc_info.value.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    assert "File size exceeds the 15 MB limit" in exc_info.value.detail


@pytest.mark.asyncio
async def test_upload_file_rejected_oversized_chunked_stream():
    """Verify that oversized files without content-length header are caught by chunked streaming."""
    sixteen_mb = 16 * 1024 * 1024

    class MockLargeStream(io.RawIOBase):
        def __init__(self, size: int):
            self.remaining = size

        def read(self, n=-1):
            if self.remaining <= 0:
                return b""
            chunk_size = min(n if n and n > 0 else self.remaining, self.remaining)
            self.remaining -= chunk_size
            return b"A" * chunk_size

        def seek(self, offset, whence=0):
            return 0

    file = UploadFile(
        filename="large_statement.csv",
        file=MockLargeStream(sixteen_mb),
        headers={"content-type": "text/csv"},
    )

    with pytest.raises(HTTPException) as exc_info:
        await validate_upload_file(file)

    assert exc_info.value.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    assert "File size exceeds the 15 MB limit" in exc_info.value.detail


@pytest.mark.asyncio
async def test_upload_file_valid_extensions():
    """Verify that valid extensions (.csv, .pdf, .xls, .xlsx) pass validation."""
    for valid_name in ["statement.csv", "statement.pdf", "statement.xls", "statement.xlsx"]:
        file = UploadFile(
            filename=valid_name,
            file=io.BytesIO(b"sample content"),
            headers={"content-type": "text/plain"},
        )
        await validate_upload_file(file)
