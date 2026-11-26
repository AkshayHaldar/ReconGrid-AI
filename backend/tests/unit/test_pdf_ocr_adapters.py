"""Unit tests for PDF OCR adapters (Gemini, OpenAI Vision, OCR.space) and error handling."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.core.config import settings
from app.utils.pdf_parser import BankPdfParser


def _make_fake_pdf(page_count: int = 1):
    pages = []
    for _ in range(page_count):
        page = MagicMock()
        page.to_image.return_value = SimpleNamespace(original=Image.new("RGB", (16, 16), "white"))
        pages.append(page)
    return SimpleNamespace(pages=pages)


def test_ocr_gemini_uses_configurable_model():
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": '[{"date": "2026-08-24", "description": "CMS/002938491801/HDFC", "utr": "CMS002938491801", "amount": 49100.0, "direction": "CREDIT"}]'
                        }
                    ]
                }
            }
        ]
    }
    post_mock = MagicMock(return_value=mock_resp)

    with (
        patch.object(settings, "OCR_PROVIDER", "gemini"),
        patch.object(settings, "OCR_GEMINI_MODEL", "gemini-2.5-flash"),
        patch.object(settings, "GEMINI_API_KEY", "gem-secret-key"),
        patch("httpx.Client.post", post_mock),
    ):
        rows = BankPdfParser._extract_via_ocr(_make_fake_pdf())

    assert len(rows) == 1
    assert rows[0]["amount"] == Decimal("49100.00")
    assert rows[0]["utr"] == "CMS002938491801"
    assert "models/gemini-2.5-flash:generateContent" in post_mock.call_args.args[0]
    assert post_mock.call_args.kwargs["headers"]["x-goog-api-key"] == "gem-secret-key"


def test_ocr_openai_vision_adapter():
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '[{"date": "2026-08-25", "description": "NEFT-CMS002938491809", "utr": "CMS002938491809", "amount": "25000.50", "direction": "CREDIT"}]'
                }
            }
        ]
    }
    post_mock = MagicMock(return_value=mock_resp)

    with (
        patch.object(settings, "OCR_PROVIDER", "openai"),
        patch.object(settings, "OCR_API_KEY", "sk-openai-ocr"),
        patch.object(settings, "OCR_OPENAI_MODEL", "gpt-4o-mini"),
        patch.object(settings, "OCR_OPENAI_BASE_URL", "https://api.openai.com/v1"),
        patch("httpx.Client.post", post_mock),
    ):
        rows = BankPdfParser._extract_via_ocr(_make_fake_pdf())

    assert len(rows) == 1
    assert rows[0]["amount"] == Decimal("25000.50")
    assert rows[0]["direction"] == "CREDIT"
    assert post_mock.call_args.args[0] == "https://api.openai.com/v1/chat/completions"
    assert post_mock.call_args.kwargs["headers"]["Authorization"] == "Bearer sk-openai-ocr"
    assert post_mock.call_args.kwargs["json"]["model"] == "gpt-4o-mini"


def test_ocr_space_adapter():
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {
        "IsErroredOnProcessing": False,
        "ParsedResults": [
            {"ParsedText": "24/08/2026 NEFT CMS002938491801 RAZORPAY CR 15000.00"},
        ],
    }
    post_mock = MagicMock(return_value=mock_resp)

    with (
        patch.object(settings, "OCR_PROVIDER", "ocr_space"),
        patch.object(settings, "OCR_API_KEY", "ocr-space-key"),
        patch("httpx.Client.post", post_mock),
    ):
        rows = BankPdfParser._extract_via_ocr(_make_fake_pdf())

    assert len(rows) == 1
    assert rows[0]["amount"] == Decimal("15000.00")
    assert rows[0]["direction"] == "CREDIT"
    assert rows[0]["utr"] == "CMS002938491801"
    assert post_mock.call_args.args[0] == "https://api.ocr.space/parse/image"
    assert post_mock.call_args.kwargs["headers"]["apikey"] == "ocr-space-key"
    assert post_mock.call_args.kwargs["data"]["base64Image"].startswith("data:image/png;base64,")


def test_ocr_unsupported_provider_raises_clear_error():
    with patch.object(settings, "OCR_PROVIDER", "invalid_engine"):
        with pytest.raises(ValueError, match="Unsupported OCR_PROVIDER"):
            BankPdfParser._extract_via_ocr(_make_fake_pdf())
