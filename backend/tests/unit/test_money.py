"""Unit tests for strict Decimal financial utilities."""

from decimal import Decimal
import pytest
from app.utils.money import format_inr, is_amount_matching, paise_to_rupees, rupees_to_paise, to_decimal


def test_to_decimal_precision():
    assert to_decimal("12450.50") == Decimal("12450.50")
    assert to_decimal(100) == Decimal("100.00")
    assert to_decimal(None) == Decimal("0.00")
    assert to_decimal("1,42,85,900.00") == Decimal("14285900.00")
    assert to_decimal("1,23,456.78") == Decimal("123456.78")
    assert to_decimal("12,34,56,789.50") == Decimal("123456789.50")
    assert to_decimal("₹ 1,23,456.78") == Decimal("123456.78")
    assert to_decimal("(1,23,456.78)") == Decimal("-123456.78")


def test_paise_conversions():
    # 500000 paise = 5,000.00 INR
    assert paise_to_rupees(500000) == Decimal("5000.00")
    assert rupees_to_paise(Decimal("5000.00")) == 500000
    assert paise_to_rupees(9820050) == Decimal("98200.50")
    assert rupees_to_paise("98200.50") == 9820050


def test_amount_matching_tolerance():
    amt1 = Decimal("1000.00")
    amt2 = Decimal("1000.50")
    amt3 = Decimal("1002.00")

    assert is_amount_matching(amt1, amt2, tolerance=Decimal("1.00")) is True
    assert is_amount_matching(amt1, amt3, tolerance=Decimal("1.00")) is False


def test_format_inr():
    assert format_inr(Decimal("14285900.00")) == "₹ 1,42,85,900.00"
    assert format_inr(Decimal("98200.00")) == "₹ 98,200.00"
    assert format_inr(Decimal("-15000.00")) == "(₹ 15,000.00)"
