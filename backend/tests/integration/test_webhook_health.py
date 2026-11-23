"""Gateway pulse: /webhooks/recent and /webhooks/health, including refused deliveries."""

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.api.v1 import webhooks
from app.core.config import settings
from app.main import app
from app.models.webhook_event import ProcessedWebhookEvent


def sign(body: bytes) -> str:
    return hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


def settlement_event(event_id="evt_pulse_1", event_type="settlement.processed", settlement_id="setl_pulse_1"):
    payload = {
        "id": event_id,
        "event": event_type,
        "payload": {"settlement": {"entity": {"id": settlement_id, "amount": 10000, "fees": 100, "utr": "UTR123"}}},
    }
    return json.dumps(payload).encode()


async def post(client, body: bytes, signature: str | None = None):
    return await client.post(
        "/api/v1/webhooks/razorpay",
        content=body,
        headers={"X-Razorpay-Signature": sign(body) if signature is None else signature},
    )


async def add_event(event_id, event_type="settlement.processed", status="PROCESSED", age_hours=0, payload=None):
    async with webhooks.async_session_factory() as db:
        db.add(
            ProcessedWebhookEvent(
                razorpay_event_id=event_id,
                event_type=event_type,
                processing_status=status,
                payload=payload if payload is not None else {},
                received_at=datetime.now(UTC) - timedelta(hours=age_hours),
            )
        )
        await db.commit()


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def health(client):
    resp = await client.get("/api/v1/webhooks/health")
    assert resp.status_code == 200
    return resp.json()["data"]


async def test_health_is_idle_when_nothing_has_arrived(client):
    data = await health(client)
    assert data["status"] == "idle"
    assert data["last_verified_at"] is None
    assert data["last_rejected_at"] is None


async def test_health_is_live_after_a_verified_webhook(client):
    assert (await post(client, settlement_event())).status_code == 200
    data = await health(client)
    assert data["status"] == "live"
    assert data["last_verified_at"] is not None
    assert data["last_rejected_at"] is None


async def test_health_is_idle_when_the_last_webhook_is_older_than_a_day(client):
    await add_event("evt_old", age_hours=25)
    assert (await health(client))["status"] == "idle"


async def test_health_is_live_just_inside_the_window(client):
    await add_event("evt_recent", age_hours=23)
    assert (await health(client))["status"] == "live"


async def test_bad_signature_gives_warning_and_is_still_a_400(client):
    resp = await post(client, settlement_event(), signature="not-the-real-signature")
    assert resp.status_code == 400
    data = await health(client)
    assert data["status"] == "warning"
    assert data["last_rejection_reason"] == "INVALID_SIGNATURE"
    assert "Signature Verification Failed" in data["message"]


async def test_missing_signature_header_is_recorded_too(client):
    resp = await client.post("/api/v1/webhooks/razorpay", content=settlement_event())
    assert resp.status_code == 400
    assert (await health(client))["status"] == "warning"


async def test_malformed_body_with_valid_signature_gives_warning(client):
    resp = await post(client, b"{not json")
    assert resp.status_code == 400
    data = await health(client)
    assert data["status"] == "warning"
    assert data["last_rejection_reason"] == "MALFORMED_PAYLOAD"


async def test_settlement_event_without_entity_is_reported_as_malformed(client):
    body = json.dumps({"id": "evt_empty", "event": "settlement.processed", "payload": {}}).encode()
    assert (await post(client, body)).status_code == 400
    items = (await client.get("/api/v1/webhooks/recent")).json()["data"]
    assert items[0]["signature_status"] == "MALFORMED"
    assert items[0]["ingestion_status"] == "REJECTED"


async def test_a_verified_webhook_after_a_rejection_clears_the_warning(client):
    await add_event("rej_old", status=webhooks.REJECTED_SIGNATURE, age_hours=2)
    assert (await health(client))["status"] == "warning"
    await add_event("evt_after", age_hours=1)
    assert (await health(client))["status"] == "live"


async def test_a_rejection_after_a_verified_webhook_turns_live_into_warning(client):
    await add_event("evt_before", age_hours=2)
    await add_event("rej_after", status=webhooks.REJECTED_MALFORMED, age_hours=1)
    assert (await health(client))["status"] == "warning"


async def test_a_day_old_rejection_does_not_keep_the_warning(client):
    await add_event("rej_stale", status=webhooks.REJECTED_SIGNATURE, age_hours=30)
    assert (await health(client))["status"] == "idle"


async def test_recent_lists_newest_first_and_caps_at_fifteen(client):
    for i in range(20):
        await add_event(f"evt_{i:02d}", age_hours=20 - i)
    resp = await client.get("/api/v1/webhooks/recent")
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert len(items) == 15
    assert items[0]["event_id"] == "evt_19"
    assert items[-1]["event_id"] == "evt_05"
    times = [item["received_at"] for item in items]
    assert times == sorted(times, reverse=True)


async def test_recent_limit_is_validated(client):
    assert (await client.get("/api/v1/webhooks/recent?limit=0")).status_code == 422
    assert (await client.get("/api/v1/webhooks/recent?limit=3")).status_code == 200


async def test_recent_empty(client):
    resp = await client.get("/api/v1/webhooks/recent")
    assert resp.json()["data"] == []


async def test_recent_item_fields_for_a_settlement_event(client):
    body = settlement_event(settlement_id="setl_fields")
    assert (await post(client, body)).status_code == 200
    item = (await client.get("/api/v1/webhooks/recent")).json()["data"][0]
    assert item["event_id"] == "evt_pulse_1"
    assert item["event_type"] == "settlement.processed"
    assert item["settlement_id"] == "setl_fields"
    assert item["utr"] == "UTR123"
    assert item["signature_status"] == "VALID"
    assert item["ingestion_status"] == "RECONCILIATION_TRIGGERED"
    assert item["payload"]["payload"]["settlement"]["entity"]["id"] == "setl_fields"
    assert item["received_at"].endswith("Z") or "+00:00" in item["received_at"]


async def test_recent_marks_other_event_types_as_ignored(client):
    body = json.dumps({"id": "evt_payout", "event": "payout.updated", "payload": {"payout": {"entity": {}}}}).encode()
    assert (await post(client, body)).status_code == 200
    item = (await client.get("/api/v1/webhooks/recent")).json()["data"][0]
    assert item["event_type"] == "payout.updated"
    assert item["settlement_id"] is None
    assert item["ingestion_status"] == "IGNORED"
    assert item["signature_status"] == "VALID"


async def test_recent_shows_failed_reconciliation(client):
    await add_event("evt_failed", status="FAILED", payload=json.loads(settlement_event("evt_failed")))
    item = (await client.get("/api/v1/webhooks/recent")).json()["data"][0]
    assert item["ingestion_status"] == "FAILED"
    assert item["signature_status"] == "VALID"


async def test_recent_shows_the_rejected_body_for_a_bad_signature(client):
    body = settlement_event(event_id="evt_forged")
    await post(client, body, signature="bad")
    item = (await client.get("/api/v1/webhooks/recent")).json()["data"][0]
    assert item["signature_status"] == "INVALID"
    assert item["ingestion_status"] == "REJECTED"
    assert item["event_type"] == "settlement.processed"
    assert item["payload"]["raw_body"] == body.decode()
    assert item["payload"]["truncated"] is False


async def test_rejected_bodies_are_truncated(client):
    body = b"x" * (webhooks.MAX_STORED_BODY_CHARS + 100)
    await post(client, body, signature="bad")
    item = (await client.get("/api/v1/webhooks/recent")).json()["data"][0]
    assert len(item["payload"]["raw_body"]) == webhooks.MAX_STORED_BODY_CHARS
    assert item["payload"]["truncated"] is True
    assert item["event_type"] == "unknown"


async def test_the_same_rejected_delivery_is_stored_once(client):
    body = settlement_event()
    for _ in range(3):
        assert (await post(client, body, signature="bad")).status_code == 400
    async with webhooks.async_session_factory() as db:
        count = await db.scalar(select(func.count()).select_from(ProcessedWebhookEvent))
    assert count == 1


async def test_only_the_newest_rejected_rows_are_kept(client, monkeypatch):
    monkeypatch.setattr(webhooks, "MAX_REJECTED_ROWS", 3)
    for i in range(5):
        await post(client, f"body {i}".encode(), signature="bad")
    items = (await client.get("/api/v1/webhooks/recent")).json()["data"]
    assert len(items) == 3
    assert [item["payload"]["raw_body"] for item in items] == ["body 4", "body 3", "body 2"]


async def test_pruning_rejected_rows_leaves_verified_events_alone(client, monkeypatch):
    monkeypatch.setattr(webhooks, "MAX_REJECTED_ROWS", 1)
    assert (await post(client, settlement_event())).status_code == 200
    for i in range(3):
        await post(client, f"junk {i}".encode(), signature="bad")
    items = (await client.get("/api/v1/webhooks/recent")).json()["data"]
    assert sorted(item["signature_status"] for item in items) == ["INVALID", "VALID"]


async def test_a_failing_record_does_not_change_the_400(client, monkeypatch):
    def broken_factory():
        raise RuntimeError("db down")

    monkeypatch.setattr(webhooks, "async_session_factory", broken_factory)
    resp = await post(client, settlement_event(), signature="bad")
    assert resp.status_code == 400
    assert resp.json()["error"]["message"] == "Invalid webhook signature"
