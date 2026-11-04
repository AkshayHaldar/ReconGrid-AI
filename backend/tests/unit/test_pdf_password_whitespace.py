"""Passwords must reach the PDF library without destructive normalization."""

import io

import pypdf
import pytest

from app.utils.pdf_parser import BankPdfParser, PdfInvalidPasswordError, PdfPasswordRequiredError


def encrypted_pdf(password):
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt(user_password=password, owner_password="synthetic-owner-password")
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()


@pytest.mark.parametrize("password", [" bank-pass", "bank-pass ", " bank-pass ", " ", "   "])
def test_preserves_significant_password_spaces(password):
    decrypted = BankPdfParser.decrypt_pdf_bytes(encrypted_pdf(password), password=password)

    reader = pypdf.PdfReader(io.BytesIO(decrypted))
    assert not reader.is_encrypted
    assert len(reader.pages) == 1


def test_trimmed_password_does_not_unlock_spaced_password():
    with pytest.raises(PdfInvalidPasswordError):
        BankPdfParser.decrypt_pdf_bytes(encrypted_pdf(" bank-pass "), password="bank-pass")


@pytest.mark.parametrize("password", [None, ""])
def test_missing_password_still_requires_input(password):
    with pytest.raises(PdfPasswordRequiredError):
        BankPdfParser.decrypt_pdf_bytes(encrypted_pdf("bank-pass"), password=password)
