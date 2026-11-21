"""Shape checks for stored secrets, kept free of settings so config can use them at startup."""

import base64
import binascii

ENCRYPTED_PREFIX = "enc:"
NONCE_BYTES = 12
TAG_BYTES = 16


def sealed_blob(value: str) -> bytes | None:
    """Return the nonce + ciphertext bytes if `value` is shaped like `enc:` + base64(nonce + ciphertext).

    A plaintext secret that merely begins with `enc:` will not decode to at least a nonce plus
    a GCM tag, so it returns None and the caller can treat it as plaintext.
    """
    if not value.startswith(ENCRYPTED_PREFIX):
        return None
    try:
        blob = base64.urlsafe_b64decode(value[len(ENCRYPTED_PREFIX) :].encode("ascii"))
    except (binascii.Error, UnicodeEncodeError):
        return None
    return blob if len(blob) >= NONCE_BYTES + TAG_BYTES else None
