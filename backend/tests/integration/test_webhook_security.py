"""Integration tests for Razorpay Webhook HMAC security and deduplication."""

import hashlib
import hmac
import json
import pytest
from httpx import ASGITransport, AsyncClient
from app.core.config import settings
from app.main import app


def compute_signature(payload_bytes: bytes, secret: str) -> str:
    return hmac.new(key=secret.encode("utf-8"), msg=payload_bytes, digestmod=hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_webhook_valid_signature_and_deduplication():
    payload = {
        "entity": "event",
        "account_id": "acc_test",
        "event": "settlement.processed",
        "id": "evt_test_sec_001",
        "payload": {
            "settlement": {
                "entity": {
                    "id": "setl_sec_001",
                    "amount": 9820000,
                    "fees": 152542,
                    "tax": 27458,
                    "utr": "CMS002938491999",
                    "status": "processed",
                }
            }
        },
    }
    payload_bytes = json.dumps(payload).encode("utf-8")
    sig = compute_signature(payload_bytes, settings.RAZORPAY_WEBHOOK_SECRET)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First call with valid signature
        resp1 = await client.post(
            "/api/v1/webhooks/razorpay",
            content=payload_bytes,
            headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["success"] is True
        assert data1["data"]["action_taken"] == "PROCESSED_AND_RECONCILED"

        # Duplicate delivery with same event_id
        resp2 = await client.post(
            "/api/v1/webhooks/razorpay",
            content=payload_bytes,
            headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["data"]["action_taken"] == "DUPLICATE_IGNORED"


@pytest.mark.asyncio
async def test_webhook_invalid_signature_rejected():
    payload_bytes = b'{"event":"settlement.processed","id":"evt_fake"}'
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/webhooks/razorpay",
            content=payload_bytes,
            headers={"X-Razorpay-Signature": "invalid_signature_hash"},
        )
        assert resp.status_code == 400
