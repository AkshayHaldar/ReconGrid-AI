"""PDF extraction must admit the same year-first dates as the shared parser."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.utils.pdf_parser import BankPdfParser


@pytest.mark.parametrize("date", ["2026-08-24", "2026/08/24", "24/08/2026", "24-08-26", "24 Aug 2026"])
def test_table_date_formats(date):
    page = SimpleNamespace(
        extract_tables=lambda: [
            [
                ["Date", "Description", "Amount"],
                [date, "CMS002938491801", "100.00"],
            ]
        ]
    )

    rows = BankPdfParser._extract_tables_from_page(page, 1)

    assert len(rows) == 1
    assert rows[0]["date"] == datetime(2026, 8, 24, tzinfo=UTC)
    assert rows[0]["amount"] == Decimal("100.00")
    assert rows[0]["direction"] == "CREDIT"


@pytest.mark.parametrize("date", ["2026-08-24", "2026/08/24", "24/08/2026", "24-08-26", "24 Aug 2026"])
def test_text_date_formats(date):
    rows = BankPdfParser._extract_from_text_lines(f"{date} CMS002938491801 100.00 DR", 1)

    assert len(rows) == 1
    assert rows[0]["date"] == datetime(2026, 8, 24, tzinfo=UTC)
    assert rows[0]["amount"] == Decimal("100.00")
    assert rows[0]["direction"] == "DEBIT"
