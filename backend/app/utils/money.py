"""Financial Decimal utilities for strict financial correctness.

Zero float usage permitted across money handling.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Union


def to_decimal(val: Union[str, int, float, Decimal, None]) -> Decimal:
    """Converts a value safely to Decimal without intermediate float precision loss."""
    if val is None:
        return Decimal("0.00")
    if isinstance(val, Decimal):
        return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if isinstance(val, float):
        # Enforce stringification to prevent binary float representation noise
        return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if isinstance(val, (int, str)):
        clean_str = str(val).replace(",", "").strip()
        if not clean_str:
            return Decimal("0.00")
        return Decimal(clean_str).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    raise TypeError(f"Cannot convert type {type(val)} to Decimal")


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
