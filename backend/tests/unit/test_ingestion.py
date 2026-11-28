"""Upload guardrails for POST /api/v1/bank/upload."""

import io

import pytest
from fastapi import HTTPException, UploadFile
from httpx import ASGITransport, AsyncClient

from app.api.v1.bank import validate_statement_upload
from app.main import app

LIMIT_BYTES = 15 * 1024 * 1024


async def _post(filename: str, payload: bytes):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        files = {"file": (filename, io.BytesIO(payload), "text/csv")}
        return await client.post("/api/v1/bank/upload", files=files)


@pytest.mark.asyncio
async def test_upload_over_15_mb_is_rejected():
    resp = await _post("statement.csv", b"0" * (16 * 1024 * 1024))

    assert resp.status_code == 413
    assert "File size exceeds the 15 MB limit" in resp.text


@pytest.mark.asyncio
async def test_upload_with_disallowed_extension_is_rejected():
    resp = await _post("statement.exe", b"MZ")

    assert resp.status_code == 415
    assert ".csv, .pdf, .xls, .xlsx" in resp.text


@pytest.mark.asyncio
@pytest.mark.parametrize("filename", ["a.csv", "a.PDF", "march.2026.xls", "a.xlsx"])
async def test_allowed_extensions_pass_at_exactly_the_limit(filename: str):
    await validate_statement_upload(UploadFile(filename=filename, file=io.BytesIO(), size=LIMIT_BYTES))


@pytest.mark.asyncio
@pytest.mark.parametrize("filename", ["", "csv", "statement.txt", "statement.csv.zip"])
async def test_other_names_are_rejected(filename: str):
    with pytest.raises(HTTPException) as err:
        await validate_statement_upload(UploadFile(filename=filename, file=io.BytesIO(), size=1))

    assert err.value.status_code == 415


@pytest.mark.asyncio
async def test_unknown_size_is_counted_and_the_file_rewound():
    upload = UploadFile(filename="a.csv", file=io.BytesIO(b"Date,Amount\n"))

    await validate_statement_upload(upload)

    assert await upload.read() == b"Date,Amount\n"


@pytest.mark.asyncio
async def test_unknown_size_over_the_limit_is_rejected():
    upload = UploadFile(filename="a.csv", file=io.BytesIO(b"0" * (LIMIT_BYTES + 1)))

    with pytest.raises(HTTPException) as err:
        await validate_statement_upload(upload)

    assert err.value.status_code == 413
