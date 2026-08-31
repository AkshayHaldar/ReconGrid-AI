"""Financial Decimal utilities for strict financial correctness.

Zero float usage permitted across money handling.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Union


import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Optional, Tuple, Union


# Regex to strip non-numeric currency noise while preserving negative signs and decimals
CURRENCY_CLEAN_REGEX = re.compile(r"[^\d.\-()+]", re.IGNORECASE)


def to_decimal(val: Union[str, int, float, Decimal, None]) -> Decimal:
    """Converts a value safely to Decimal without intermediate float precision loss.

    Handles Indian currency notation (₹, INR, Rs., Cr/Dr suffixes, commas, parentheses).
    """
    if val is None:
        return Decimal("0.00")
    if isinstance(val, Decimal):
        return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if isinstance(val, float):
        # Enforce stringification to prevent binary float representation noise
        return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if isinstance(val, int):
        return Decimal(val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if isinstance(val, str):
        clean_str = val.strip()
        if not clean_str:
            return Decimal("0.00")

        # Check for accounting parentheses negative format e.g. (1,234.50)
        is_parentheses_neg = clean_str.startswith("(") and clean_str.endswith(")")
        if is_parentheses_neg:
            clean_str = clean_str[1:-1].strip()

        # Remove currency symbols, INR, Rs., Cr, Dr, commas, spaces, NBSP
        clean_str = (
            clean_str
            .replace("₹", "")
            .replace("INR", "")
            .replace("inr", "")
            .replace("Rs.", "")
            .replace("Rs", "")
            .replace("rs.", "")
            .replace("rs", "")
            .replace("CR", "")
            .replace("Cr", "")
            .replace("cr", "")
            .replace("DR", "")
            .replace("Dr", "")
            .replace("dr", "")
            .replace(",", "")
            .replace(" ", "")  # NBSP
            .replace("​", "")  # Zero-width space
            .strip()
        )

        if not clean_str:
            return Decimal("0.00")

        if is_parentheses_neg and not clean_str.startswith("-"):
            clean_str = f"-{clean_str}"

        try:
            return Decimal(clean_str).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except InvalidOperation:
            raise ValueError(f"Invalid monetary numeric format: '{val}'")

    raise TypeError(f"Cannot convert type {type(val)} to Decimal")


def parse_amount_and_direction(raw_val: Any) -> Tuple[Decimal, str]:
    """Parses raw amount string and extracts absolute Decimal amount and direction (CREDIT/DEBIT)."""
    if raw_val is None:
        return Decimal("0.00"), "CREDIT"

    raw_str = str(raw_val).strip().upper()
    if not raw_str:
        return Decimal("0.00"), "CREDIT"

    is_debit = (
        raw_str.endswith(" DR")
        or raw_str.endswith("DR")
        or raw_str.startswith("DR ")
        or raw_str.startswith("-")
        or (raw_str.startswith("(") and raw_str.endswith(")"))
    )

    amount = abs(to_decimal(raw_val))
    direction = "DEBIT" if is_debit else "CREDIT"
    return amount, direction


def paise_to_rupees(paise: Union[int, str, Decimal]) -> Decimal:
    """Converts Razorpay paise (integer) to INR Rupees Decimal with 2 decimal places."""
    dec_paise = to_decimal(paise)
    return (dec_paise / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def rupees_to_paise(rupees: Union[str, Decimal, int]) -> int:
    """Converts INR Rupees Decimal to Razorpay paise integer."""
    dec_rupees = to_decimal(rupees)
    return int((dec_rupees * Decimal("100")).to_integral_value(rounding=ROUND_HALF_UP))


def is_amount_matching(
    amount1: Decimal,
    amount2: Decimal,
    tolerance: Decimal = Decimal("1.00"),
) -> bool:
    """Checks if two amounts match within the specified tolerance."""
    return abs(amount1 - amount2) <= tolerance


def format_inr(amount: Decimal) -> str:
    """Formats a Decimal amount as Indian Rupee string (e.g. ₹ 1,42,85,900.00)."""
    amount = to_decimal(amount)
    is_negative = amount < Decimal("0.00")
    abs_amt = abs(amount)

    s = f"{abs_amt:.2f}"
    int_part, dec_part = s.split(".")

    if len(int_part) <= 3:
        formatted_int = int_part
    else:
        last3 = int_part[-3:]
        remaining = int_part[:-3]
        groups = []
        while len(remaining) > 2:
            groups.insert(0, remaining[-2:])
            remaining = remaining[:-2]
        if remaining:
            groups.insert(0, remaining)
        formatted_int = ",".join(groups) + "," + last3

    res = f"₹ {formatted_int}.{dec_part}"
    return f"({res})" if is_negative else res


class UnscaledPaiseAmountError(ValueError):
    """Raised when an amount string appears to be unscaled paise instead of INR rupees."""
    pass


def validate_raw_amount_format(raw_val: Any, col_name: str = "", row_idx: int = 1) -> None:
    """Validates that a raw amount string is not an unscaled integer paise amount.
    
    Heuristic:
    - If raw value is an unscaled integer (no decimal point) AND >= 100,000 OR column name indicates paise,
      it is rejected as unscaled paise.
    - Legitimate large rupee transactions with decimal formatting (e.g. 500000.00) pass safely.
    """
    if raw_val is None:
        return
    raw_str = str(raw_val).strip()
    if not raw_str:
        return

    clean_val = (
        raw_str
        .replace(",", "")
        .replace("₹", "")
        .replace("INR", "")
        .replace("inr", "")
        .replace("Rs.", "")
        .replace("Rs", "")
        .replace("CR", "")
        .replace("Cr", "")
        .replace("cr", "")
        .replace("DR", "")
        .replace("Dr", "")
        .replace("dr", "")
        .strip()
    )

    # Check if column explicitly indicates paise formatting
    col_lower = col_name.lower()
    is_paise_col = "paise" in col_lower or "paisa" in col_lower

    has_decimal_point = "." in clean_val
    is_integer_format = clean_val.isdigit() or (clean_val.startswith("-") and clean_val[1:].isdigit())

    if is_paise_col or (is_integer_format and not has_decimal_point and abs(int(clean_val)) >= 100000):
        raise UnscaledPaiseAmountError(
            f"Row {row_idx}: amount {raw_str} appears to be unscaled paise, expected rupees with 2 decimal places — please verify your export format"
        )


def calculate_standard_fees(
    gross_amount: Union[str, int, float, Decimal],
    mdr_rate: Decimal = Decimal("0.02"),
    gst_rate: Decimal = Decimal("0.18"),
) -> tuple[Decimal, Decimal, Decimal]:
    """Calculates standard Razorpay fees (2% MDR + 18% GST on MDR) and net settlement payout.
    
    Formula:
        fee = (gross * 0.02) rounded to 2 decimal places (ROUND_HALF_UP)
        gst = (fee * 0.18) rounded to 2 decimal places (ROUND_HALF_UP)
        net = gross - fee - gst
    
    Returns: (fees, gst_tax, net_amount) as quantized Decimals.
    """
    gross = to_decimal(gross_amount)
    fee = (gross * mdr_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    gst = (fee * gst_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    net = (gross - fee - gst).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return fee, gst, net
