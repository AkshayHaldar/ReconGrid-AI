"""Unit tests for fuzzy descriptor matching."""

from app.utils.fuzzy import compute_string_similarity, is_fuzzy_match, normalize_descriptor


def test_normalize_descriptor():
    raw = "RTGS/CMS002938491801/HDFC/RAZORPAY SOFTWARE PVT"
    norm = normalize_descriptor(raw)
    assert "RAZORPAY" in norm
    assert "SOFTWARE" in norm
    assert "/" not in norm


def test_fuzzy_match_threshold():
    str1 = "RTGS RAZORPAY SOFTWARE PRIVATE LIMITED BANGALORE"
    str2 = "RTGS RAZORPAY SOFTWARE PRIVATE LIMITED BANGLORE 94"

    matched, score = is_fuzzy_match(str1, str2, threshold=0.90)
    assert matched is True
    assert score >= 0.90


def test_fuzzy_mismatch():
    str1 = "CMS HDFC SALARY TRANSFER"
    str2 = "RAZORPAY PAYMENT GATEWAY PAYOUT"

    matched, score = is_fuzzy_match(str1, str2, threshold=0.90)
    assert matched is False
    assert score < 0.50
