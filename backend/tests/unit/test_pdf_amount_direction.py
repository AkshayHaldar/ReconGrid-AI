"""Generic PDF amount cells must preserve bank debit/credit indicators."""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.utils.pdf_parser import BankPdfParser


@pytest.mark.parametrize(
    ("raw_amount", "direction"),
    [
        ("100.00 DR", "DEBIT"),
        ("100.00 dr", "DEBIT"),
        ("DR 100.00", "DEBIT"),
        ("-100.00", "DEBIT"),
        ("(100.00)", "DEBIT"),
        ("100.00 CR", "CREDIT"),
        ("100.00 cr", "CREDIT"),
        ("100.00", "CREDIT"),
    ],
)
def test_generic_table_amount_direction(raw_amount, direction):
    page = SimpleNamespace(
        extract_tables=lambda: [
            [
                ["Date", "Description", "Amount"],
                ["24/08/2026", "CMS002938491801", raw_amount],
            ]
        ]
    )

    rows = BankPdfParser._extract_tables_from_page(page, 1)

    assert len(rows) == 1
    assert rows[0]["amount"] == Decimal("100.00")
    assert rows[0]["direction"] == direction
