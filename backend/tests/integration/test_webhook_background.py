"""Webhook acknowledgements precede reconciliation and commit durable dedup state."""

import asyncio
import hashlib
import hmac
import json
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.api.v1 import webhooks
from app.core.config import settings
from app.main import app
from app.models.razorpay_settlement import RazorpaySettlement
from app.models.webhook_event import ProcessedWebhookEvent


def signed_event(event_id="evt_background", event_type="settlement.processed"):
    payload = {
        "id": event_id,
        "event": event_type,
        "payload": {"settlement": {"entity": {"id": "setl_background", "amount": 10000, "fees": 100, "tax": 18}}},
    }
    if event_id is None:
        del payload["id"]
    body = json.dumps(payload).encode()
    sig = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return {"content": body, "headers": {"X-Razorpay-Signature": sig, "Content-Type": "application/json"}}


async def stored_status(event_id):
    async with webhooks.async_session_factory() as db:
        return await db.scalar(
            select(ProcessedWebhookEvent.processing_status).where(ProcessedWebhookEvent.razorpay_event_id == event_id)
        )


async def settlement_count():
    async with webhooks.async_session_factory() as db:
        return await db.scalar(select(func.count()).select_from(RazorpaySettlement))


@pytest.mark.asyncio
async def test_ack_is_sent_before_blocked_reconciliation_and_event_is_committed(monkeypatch):
    started, released, entered = asyncio.Event(), asyncio.Event(), asyncio.Event()
    monkeypatch.setattr(webhooks.BankRepository, "get_all_by_batch", AsyncMock(return_value=[object()]))

    async def slow_reconcile(*args, **kwargs):
        entered.set()
        await released.wait()

    reconcile = AsyncMock(side_effect=slow_reconcile)
    monkeypatch.setattr(webhooks.ReconciliationEngine, "reconcile_batch", reconcile)
    messages = []

    async def observed_app(scope, receive, send):
        async def observed_send(message):
            if message["type"] in {"http.response.start", "http.response.body"}:
                messages.append(message)
                if message["type"] == "http.response.body" and not message.get("more_body", False):
                    started.set()
            await send(message)

        await app(scope, receive, observed_send)

    async with AsyncClient(transport=ASGITransport(app=observed_app), base_url="http://test") as client:
        request = asyncio.create_task(client.post("/api/v1/webhooks/razorpay", **signed_event()))
        try:
            await asyncio.wait_for(started.wait(), 2)
            await asyncio.wait_for(entered.wait(), 2)
            assert messages[0]["status"] == 200
            assert json.loads(messages[-1]["body"])["data"]["status"] == "queued"
            # A separate DB session sees the event even while the request task is open.
            assert await stored_status("evt_background") == "QUEUED"
            assert not request.done()
        finally:
            released.set()
            await request
    assert await stored_status("evt_background") == "PROCESSED"
    assert await settlement_count() == 1
    reconcile.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_background_work_rolls_back_and_same_event_can_retry(monkeypatch):
    monkeypatch.setattr(webhooks.BankRepository, "get_all_by_batch", AsyncMock(return_value=[object()]))
    reconcile = AsyncMock(side_effect=[RuntimeError("synthetic failure"), []])
    monkeypatch.setattr(webhooks.ReconciliationEngine, "reconcile_batch", reconcile)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post("/api/v1/webhooks/razorpay", **signed_event())
        assert first.status_code == 200
        assert await stored_status("evt_background") == "FAILED"
        assert await settlement_count() == 0
        retry = await client.post("/api/v1/webhooks/razorpay", **signed_event())
        assert retry.json()["data"]["status"] == "queued"
        assert await stored_status("evt_background") == "PROCESSED"
        assert await settlement_count() == 1
        duplicate = await client.post("/api/v1/webhooks/razorpay", **signed_event())
        assert duplicate.json()["data"]["action_taken"] == "DUPLICATE_IGNORED"
        assert reconcile.await_count == 2


@pytest.mark.asyncio
async def test_unsupported_event_is_recorded_without_reconciliation(monkeypatch):
    reconcile = AsyncMock()
    monkeypatch.setattr(webhooks, "reconcile_webhook_event", reconcile)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/webhooks/razorpay", **signed_event(event_type="payment.authorized"))
    assert response.status_code == 200
    assert response.json()["data"]["action_taken"] == "EVENT_RECORDED"
    assert await stored_status("evt_background") == "PROCESSED"
    reconcile.assert_not_awaited()


@pytest.mark.asyncio
async def test_event_without_id_uses_stable_digest_for_duplicate_delivery():
    event = signed_event(event_id=None)
    expected = hashlib.sha256(event["content"]).hexdigest()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post("/api/v1/webhooks/razorpay", **event)
        second = await client.post("/api/v1/webhooks/razorpay", **event)
    assert first.json()["data"]["event_id"] == expected
    assert second.json()["data"]["action_taken"] == "DUPLICATE_IGNORED"
    assert await settlement_count() == 1


@pytest.mark.asyncio
async def test_simultaneous_duplicate_deliveries_queue_only_one_reconciliation(monkeypatch):
    monkeypatch.setattr(webhooks.BankRepository, "get_all_by_batch", AsyncMock(return_value=[object()]))
    reconcile = AsyncMock(return_value=[])
    monkeypatch.setattr(webhooks.ReconciliationEngine, "reconcile_batch", reconcile)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        results = await asyncio.gather(*(client.post("/api/v1/webhooks/razorpay", **signed_event()) for _ in range(3)))
    assert all(response.status_code == 200 for response in results)
    actions = [response.json()["data"]["action_taken"] for response in results]
    assert actions.count("RECONCILIATION_QUEUED") == 1
    assert actions.count("DUPLICATE_IGNORED") == 2
    reconcile.assert_awaited_once()
    assert await stored_status("evt_background") == "PROCESSED"
    assert await settlement_count() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [[], {"payload": None}, {"payload": {"settlement": {"entity": []}}}, {"id": 42}])
async def test_signed_malformed_payload_does_not_queue_or_persist(payload, monkeypatch):
    body = json.dumps(payload).encode()
    signature = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    reconcile = AsyncMock()
    monkeypatch.setattr(webhooks, "reconcile_webhook_event", reconcile)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.post(
            "/api/v1/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": signature}
        )
    assert result.status_code == 400
    reconcile.assert_not_awaited()
    async with webhooks.async_session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(ProcessedWebhookEvent)) == 0
