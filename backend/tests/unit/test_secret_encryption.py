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


def test_plaintext_that_starts_with_enc_prefix_is_returned_as_is(master_key):
    # Too short to be nonce + tag, so it cannot be ciphertext.
    assert security.resolve_secret("enc:my-plain-secret") == "enc:my-plain-secret"
    assert security.resolve_secret("enc:") == "enc:"


def test_real_ciphertext_with_wrong_key_still_raises(master_key, monkeypatch):
    token = security.encrypt_secret("abc")
    monkeypatch.setattr(settings, "ENCRYPTION_MASTER_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    with pytest.raises(ValueError):
        security.resolve_secret(token)


def test_mask_secret_zero_suffix_does_not_leak_the_value():
    masked = security.mask_secret("rzp_test_ABCDEFGHIJ1a2b", visible_suffix=0)
    assert "ABCDEFGHIJ" not in masked
    assert "1a2b" not in masked
    assert masked.startswith("rzp_test")
    assert len(masked) == len("rzp_test_ABCDEFGHIJ1a2b")


def test_settings_reject_encrypted_secret_without_master_key():
    from app.core.config import Settings

    token_like = "enc:" + base64.urlsafe_b64encode(os.urandom(40)).decode()
    with pytest.raises(ValueError, match="ENCRYPTION_MASTER_KEY"):
        Settings(RAZORPAY_KEY_SECRET=token_like, ENCRYPTION_MASTER_KEY="", _env_file=None)
    good = base64.urlsafe_b64encode(os.urandom(32)).decode()
    Settings(RAZORPAY_KEY_SECRET=token_like, ENCRYPTION_MASTER_KEY=good, _env_file=None)
    # Plaintext secrets need no key.
    Settings(RAZORPAY_KEY_SECRET="plain", ENCRYPTION_MASTER_KEY="", _env_file=None)
