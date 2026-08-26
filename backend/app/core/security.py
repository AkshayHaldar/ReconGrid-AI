"""Cryptographic security and webhook signature verification."""

import hashlib
import hmac
from fastapi import Header, HTTPException, Request, status
from app.core.config import settings
from app.core.logging import logger


def verify_razorpay_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    """Verifies Razorpay HMAC SHA-256 signature using constant-time comparison."""
    if not signature or not secret:
        return False
    expected = hmac.new(
        key=secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


async def razorpay_webhook_guard(
    request: Request,
    x_razorpay_signature: str = Header(default="", alias="X-Razorpay-Signature"),
) -> bytes:
    """FastAPI dependency to guard Razorpay webhook endpoints against forged payloads."""
    raw_body = await request.body()
    if not x_razorpay_signature or not verify_razorpay_signature(
        raw_body, x_razorpay_signature, settings.RAZORPAY_WEBHOOK_SECRET
    ):
        logger.warning(
            "webhook_signature_verification_failed",
            received_signature_len=len(x_razorpay_signature),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature",
        )
    return raw_body
