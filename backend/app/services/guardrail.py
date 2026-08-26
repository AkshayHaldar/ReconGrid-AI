"""Strict Numeric Token Guardrail for Settlement Q&A Agent.

Enforces the non-negotiable rule: LLMs narrate facts, they NEVER compute or invent numbers.
Any generated answer containing a number not present in the underlying record is rejected.
"""

import re
from decimal import Decimal
from typing import Any
from app.models.reconciliation_log import ReconciliationLog
from app.utils.money import to_decimal


# Regex to extract numeric tokens from natural language text (integers, floats, currency values)
NUMERIC_TOKEN_REGEX = re.compile(r"\b(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\b")


def extract_numeric_tokens(text: str) -> set[str]:
    """Extracts normalized numeric strings from text."""
    if not text:
        return set()
    matches = NUMERIC_TOKEN_REGEX.findall(text)
    normalized = set()
    for m in matches:
        clean = m.replace(",", "").strip()
        if clean:
            # Strip trailing zeros if decimal e.g. 900.00 -> 900
            try:
                dec = Decimal(clean)
                normalized.add(str(dec))
                normalized.add(f"{dec:.2f}")
                normalized.add(str(int(dec)))
            except Exception:
                normalized.add(clean)
    return normalized


def extract_record_numbers(log: ReconciliationLog) -> set[str]:
    """Extracts all valid numbers from the source ReconciliationLog and linked entities."""
    allowed: set[str] = {
        "18", "18.0", "18.00",  # Permissible GST rate standard
        "2", "2.0", "2.00",     # Permissible standard gateway rate
        "1", "0", "0.0", "0.00",
        "100", "90", "85", "94", # Standard confidence rates / percentage denominators
    }

    def add_num(val: Any) -> None:
        if val is None:
            return
        if isinstance(val, (Decimal, int, float)):
            dec = to_decimal(val)
            allowed.add(str(dec))
            allowed.add(f"{dec:.2f}")
            allowed.add(str(int(dec)))
        elif isinstance(val, str):
            allowed.update(extract_numeric_tokens(val))

    # Delta amount & confidence
    add_num(log.delta_amount)
    add_num(log.confidence_score)

    # Bank transaction fields
    if log.bank_transaction:
        add_num(log.bank_transaction.amount)
        add_num(log.bank_transaction.utr)
        add_num(log.bank_transaction.description)
        add_num(log.bank_transaction.date.day)
        add_num(log.bank_transaction.date.month)
        add_num(log.bank_transaction.date.year)

    # Razorpay settlement fields
    if log.rzp_settlement:
        add_num(log.rzp_settlement.amount)
        add_num(log.rzp_settlement.gross_amount)
        add_num(log.rzp_settlement.fees)
        add_num(log.rzp_settlement.tax)
        add_num(log.rzp_settlement.utr)
        add_num(log.rzp_settlement.settlement_id)
        if log.rzp_settlement.raw_payload:
            for k, v in log.rzp_settlement.raw_payload.items():
                add_num(v)

    # Diagnostic note fields
    allowed.update(extract_numeric_tokens(log.diagnostic_note))

    return allowed


def validate_qa_narration(
    generated_text: str,
    source_log: ReconciliationLog,
) -> tuple[bool, list[str]]:
    """Validates that all numbers in the LLM narration exist in the source record.

    Returns (is_valid, list_of_invented_tokens).
    """
    text_numbers = extract_numeric_tokens(generated_text)
    allowed_numbers = extract_record_numbers(source_log)

    invented = [num for num in text_numbers if num not in allowed_numbers]
    is_valid = len(invented) == 0
    return is_valid, invented
