"""Secret encryption helpers and masking."""

import base64
import os

import pytest

from app.core import security
from app.core.config import settings


@pytest.fixture
def master_key(monkeypatch):
    key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    monkeypatch.setattr(settings, "ENCRYPTION_MASTER_KEY", key)
    return key


def test_roundtrip(master_key):
    token = security.encrypt_secret("super-secret-value")
    assert token.startswith("enc:")
    assert "super-secret-value" not in token
    assert security.decrypt_secret(token) == "super-secret-value"


def test_same_plaintext_encrypts_differently(master_key):
    assert security.encrypt_secret("abc") != security.encrypt_secret("abc")


def test_wrong_key_is_rejected(master_key, monkeypatch):
    token = security.encrypt_secret("abc")
    monkeypatch.setattr(settings, "ENCRYPTION_MASTER_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    with pytest.raises(ValueError):
        security.decrypt_secret(token)


def test_tampered_token_is_rejected(master_key):
    token = security.encrypt_secret("abc")
    with pytest.raises(ValueError):
        security.decrypt_secret(token[:-4] + "AAAA")


def test_missing_or_short_key(monkeypatch):
    monkeypatch.setattr(settings, "ENCRYPTION_MASTER_KEY", "")
    with pytest.raises(ValueError):
        security.encrypt_secret("abc")
    monkeypatch.setattr(settings, "ENCRYPTION_MASTER_KEY", base64.urlsafe_b64encode(b"short").decode())
    with pytest.raises(ValueError):
        security.encrypt_secret("abc")


def test_resolve_secret_passes_plaintext_through(master_key):
    assert security.resolve_secret("plain") == "plain"
    assert security.resolve_secret(security.encrypt_secret("hidden")) == "hidden"


def test_mask_secret_format():
    masked = security.mask_secret("rzp_test_ABCDEFGHIJ1a2b")
    assert masked.startswith("rzp_test")
    assert masked.endswith("1a2b")
    assert "ABCDEFGHIJ" not in masked
    assert len(masked) == len("rzp_test_ABCDEFGHIJ1a2b")


def test_mask_secret_short_and_empty():
    assert security.mask_secret("") == ""
    assert "abc" not in security.mask_secret("abc")
