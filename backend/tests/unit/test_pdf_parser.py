"""Unit tests for BankPdfParser and PDF Ingestion."""

import io
from decimal import Decimal
import pytest
import pypdf
from app.utils.pdf_parser import (
    BANK_PASSWORD_FORMATS,
    BankPdfParser,
    PdfInvalidPasswordError,
    PdfPasswordRequiredError,
)


def create_mock_pdf(text_content: str, password: str | None = None) -> bytes:
    """Helper to create a simple mock PDF in-memory with optional encryption."""
    # Create a basic valid PDF using pypdf
    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    
    if password:
        writer.encrypt(user_password=password, owner_password=password + "_owner")
    
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_bank_password_formats_catalog():
    assert len(BANK_PASSWORD_FORMATS) >= 5
    banks = [b["bank"] for b in BANK_PASSWORD_FORMATS]
    assert "HDFC Bank" in banks
    assert "ICICI Bank" in banks
    assert "State Bank of India (SBI)" in banks
    assert "Axis Bank" in banks


def test_pdf_password_required_on_encrypted():
    encrypted_pdf = create_mock_pdf("Sample text", password="mypassword123")
    with pytest.raises(PdfPasswordRequiredError):
        BankPdfParser.decrypt_pdf_bytes(encrypted_pdf, password=None)

    with pytest.raises(PdfPasswordRequiredError):
        BankPdfParser.decrypt_pdf_bytes(encrypted_pdf, password="")


def test_pdf_invalid_password():
    encrypted_pdf = create_mock_pdf("Sample text", password="correct_password")
    with pytest.raises(PdfInvalidPasswordError):
        BankPdfParser.decrypt_pdf_bytes(encrypted_pdf, password="wrong_password")


def test_pdf_successful_decryption():
    encrypted_pdf = create_mock_pdf("Sample text", password="correct_password")
    decrypted = BankPdfParser.decrypt_pdf_bytes(encrypted_pdf, password="correct_password")
    assert isinstance(decrypted, bytes)
    assert len(decrypted) > 0
    reader = pypdf.PdfReader(io.BytesIO(decrypted))
    assert not reader.is_encrypted
