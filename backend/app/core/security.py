"""Cryptographic security and webhook signature verification."""

import hashlib
import hmac
import ipaddress

from fastapi import Header, HTTPException, Request, status

from app.core.config import settings
from app.core.logging import logger


def is_internal_ip(client_ip: str | None) -> bool:
    """Checks whether an IP address belongs to loopback or RFC1918 private subnets."""
    if not client_ip:
        return False
    if client_ip in ("localhost", "testclient", "127.0.0.1", "::1"):
        return True
    try:
        ip = ipaddress.ip_address(client_ip)
        return ip.is_loopback or ip.is_private
    except ValueError:
        return False


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


async def metrics_access_guard(
    request: Request,
    authorization: str | None = Header(default=None),
) -> None:
    """Protects the /metrics endpoint with optional internal bearer token or internal network check."""
    expected_token = settings.METRICS_BEARER_TOKEN.strip()
    if not expected_token:
        return

    # 1. Bearer Token Check
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            if hmac.compare_digest(parts[1], expected_token):
                return

    # 2. Internal Network Check (Client IP or X-Forwarded-For)
    client_ip = None
    if request.client:
        client_ip = request.client.host
    if not client_ip and "x-forwarded-for" in request.headers:
        client_ip = request.headers["x-forwarded-for"].split(",")[0].strip()

    if client_ip and (client_ip in settings.METRICS_INTERNAL_IPS or is_internal_ip(client_ip)):
        return

    logger.warning("metrics_unauthorized_access_attempt", client_ip=client_ip)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized metrics access. Valid Bearer token or internal network required.",
        headers={"WWW-Authenticate": "Bearer"},
    )
