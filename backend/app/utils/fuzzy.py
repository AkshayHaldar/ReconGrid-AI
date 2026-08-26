"""Fuzzy string matching utilities for Tier 2 descriptor reconciliation."""

import difflib
import re


def normalize_descriptor(text: str | None) -> str:
    """Normalizes bank narrative or Razorpay descriptor for robust string matching."""
    if not text:
        return ""
    # Strip common transaction prefixes and punctuation
    cleaned = re.sub(r"[^A-Za-z0-9]", " ", text.upper())
    # Remove excessive whitespace
    tokens = [t for t in cleaned.split() if t not in {"CMS", "NEFT", "RTGS", "IMPS", "UPI", "CR", "DR", "INF"}]
    return " ".join(tokens)


def compute_string_similarity(str1: str | None, str2: str | None) -> float:
    """Computes normalized similarity ratio between two descriptor strings (0.0 to 1.0)."""
    if not str1 or not str2:
        return 0.0

    norm1 = normalize_descriptor(str1)
    norm2 = normalize_descriptor(str2)

    if not norm1 or not norm2:
        # Fallback to direct raw comparison if token filtering emptied string
        norm1 = str1.strip().upper()
        norm2 = str2.strip().upper()

    if norm1 == norm2:
        return 1.0

    matcher = difflib.SequenceMatcher(None, norm1, norm2)
    return round(matcher.ratio(), 4)


def is_fuzzy_match(
    str1: str | None,
    str2: str | None,
    threshold: float = 0.90,
) -> tuple[bool, float]:
    """Determines whether two descriptors meet the fuzzy match threshold."""
    score = compute_string_similarity(str1, str2)
    return score >= threshold, score
