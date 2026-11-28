"""The outbox worker recovers QUEUED webhook events and never reconciles an event twice."""

import asyncio
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.exc import OperationalError

from app import worker
from app.api.v1 import webhooks
from app.core.config import settings
from app.main import app
from app.models.razorpay_settlement import RazorpaySettlement
from app.models.webhook_event import ProcessedWebhookEvent


def event_payload(event_id: str) -> dict:
    return {
        "id": event_id,
        "event": "settlement.processed",
        "payload": {"settlement": {"entity": {"id": "setl_" + event_id, "amount": 10000, "fees": 100, "tax": 18}}},
    }


def signed(payload: dict) -> dict:
    body = json.dumps(payload).encode()
    sig = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return {"content": body, "headers": {"X-Razorpay-Signature": sig, "Content-Type": "application/json"}}


async def queue_events(*event_ids: str, age: timedelta = timedelta(0)) -> None:
    """Rows exactly as the webhook route leaves them, last touched `age` ago."""
    touched = datetime.now(UTC) - age
    async with webhooks.async_session_factory() as db:
        for event_id in event_ids:
            db.add(
                ProcessedWebhookEvent(
                    razorpay_event_id=event_id,
                    event_type="settlement.processed",
                    processing_status="QUEUED",
                    payload=event_payload(event_id),
                    received_at=touched,
                    created_at=touched,
                    updated_at=touched,
                )
            )
        await db.commit()


async def age_event(event_id: str, age: timedelta) -> None:
    async with webhooks.async_session_factory() as db:
        await db.execute(
            update(ProcessedWebhookEvent)
            .where(ProcessedWebhookEvent.razorpay_event_id == event_id)
            .values(updated_at=datetime.now(UTC) - age)
        )
        await db.commit()


async def statuses() -> dict[str, str]:
    async with webhooks.async_session_factory() as db:
        rows = await db.execute(
            select(ProcessedWebhookEvent.razorpay_event_id, ProcessedWebhookEvent.processing_status)
        )
        return {event_id: status for event_id, status in rows.all()}


async def settlement_ids() -> list[str]:
    async with webhooks.async_session_factory() as db:
        return sorted((await db.scalars(select(RazorpaySettlement.settlement_id))).all())


@pytest.fixture(autouse=True)
def worker_settings(monkeypatch):
    """Pin the defaults so a local .env cannot change what these tests mean; tests override as needed."""
    monkeypatch.setattr(settings, "WEBHOOK_INLINE_RECONCILE", True)
    monkeypatch.setattr(settings, "WEBHOOK_STALE_AFTER_SECONDS", 60)
    monkeypatch.setattr(settings, "WEBHOOK_WORKER_POLL_SECONDS", 5.0)


@pytest.fixture
def reconcile(monkeypatch):
    """Count reconcile_batch calls without running the matching engine."""
    monkeypatch.setattr(webhooks.BankRepository, "get_all_by_batch", AsyncMock(return_value=[object()]))
    mock = AsyncMock(return_value=[])
    monkeypatch.setattr(webhooks.ReconciliationEngine, "reconcile_batch", mock)
    return mock


@pytest.mark.asyncio
async def test_event_left_queued_by_a_crash_is_recovered_once_it_is_stale(reconcile):
    entered, released = asyncio.Event(), asyncio.Event()

    async def crash_midway(*args, **kwargs):
        entered.set()
        await released.wait()  # never set: the process "dies" here

    reconcile.side_effect = crash_midway
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        request = asyncio.create_task(client.post("/api/v1/webhooks/razorpay", **signed(event_payload("evt_crash"))))
        await asyncio.wait_for(entered.wait(), 2)
        # Kill the in-process background task in the middle of reconciliation.
        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request

    # The attempt was rolled back as a whole: still queued, no half-written settlement.
    assert await statuses() == {"evt_crash": "QUEUED"}
    assert await settlement_ids() == []

    reconcile.side_effect = None
    # A fresh row still belongs to the API fast path (WEBHOOK_STALE_AFTER_SECONDS=60).
    assert await worker.drain_once() == 0
    assert await statuses() == {"evt_crash": "QUEUED"}

    await age_event("evt_crash", timedelta(seconds=61))
    assert await worker.drain_once() == 1
    assert await statuses() == {"evt_crash": "PROCESSED"}
    assert await settlement_ids() == ["setl_evt_crash"]
    # Crashed attempt plus the recovery; a second drain finds nothing left to do.
    assert reconcile.await_count == 2
    assert await worker.drain_once() == 0
    assert reconcile.await_count == 2


@pytest.mark.asyncio
async def test_worker_does_not_redo_an_event_the_api_is_still_processing(reconcile):
    entered, released = asyncio.Event(), asyncio.Event()

    async def slow(*args, **kwargs):
        entered.set()
        await released.wait()

    reconcile.side_effect = slow
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        request = asyncio.create_task(client.post("/api/v1/webhooks/razorpay", **signed(event_payload("evt_busy"))))
        await asyncio.wait_for(entered.wait(), 2)
        # The worker treats the row as stale right away but must not reconcile it a second time.
        drain = asyncio.create_task(worker.drain_once(stale_after=0))
        await asyncio.sleep(0.2)
        released.set()
        response = await request
        assert await asyncio.wait_for(drain, 10) == 0
    assert response.json()["data"]["action_taken"] == "RECONCILIATION_QUEUED"
    assert await statuses() == {"evt_busy": "PROCESSED"}
    assert await settlement_ids() == ["setl_evt_busy"]
    reconcile.assert_awaited_once()


@pytest.mark.asyncio
async def test_parallel_workers_process_each_event_exactly_once(reconcile):
    event_ids = [f"evt_parallel_{index}" for index in range(5)]
    await queue_events(*event_ids, age=timedelta(minutes=5))

    results = await asyncio.wait_for(asyncio.gather(*(worker.drain_once(stale_after=60) for _ in range(3))), 30)

    assert sum(results) == 5
    assert reconcile.await_count == 5
    assert await statuses() == {event_id: "PROCESSED" for event_id in event_ids}
    assert await settlement_ids() == sorted("setl_" + event_id for event_id in event_ids)


@pytest.mark.asyncio
async def test_failing_event_is_marked_failed_and_does_not_block_the_rest(reconcile):
    await queue_events("evt_a_bad", age=timedelta(minutes=10))
    await queue_events("evt_b_good", age=timedelta(minutes=5))
    reconcile.side_effect = [RuntimeError("synthetic failure"), []]

    assert await worker.drain_once(stale_after=60) == 1

    assert await statuses() == {"evt_a_bad": "FAILED", "evt_b_good": "PROCESSED"}
    assert await settlement_ids() == ["setl_evt_b_good"]  # the failed attempt was rolled back
    # FAILED is final for the worker; a redelivery of the webhook requeues it, as before.
    assert await worker.drain_once(stale_after=0) == 0


@pytest.mark.asyncio
async def test_with_inline_reconcile_off_the_api_only_enqueues_and_the_worker_owns_the_event(monkeypatch, reconcile):
    monkeypatch.setattr(settings, "WEBHOOK_INLINE_RECONCILE", False)
    monkeypatch.setattr(settings, "WEBHOOK_STALE_AFTER_SECONDS", 3600)  # ignored without the fast path
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/webhooks/razorpay", **signed(event_payload("evt_worker_only")))
    assert response.json()["data"]["action_taken"] == "RECONCILIATION_QUEUED"
    assert await statuses() == {"evt_worker_only": "QUEUED"}
    reconcile.assert_not_awaited()

    assert worker.stale_after_seconds() == 0
    assert await worker.drain_once() == 1
    assert await statuses() == {"evt_worker_only": "PROCESSED"}
    reconcile.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_worker_drains_the_outbox_after_a_restart_and_stops_cleanly(monkeypatch, reconcile):
    # Events a previous API process accepted but never reconciled.
    await queue_events("evt_restart_1", "evt_restart_2", age=timedelta(minutes=5))
    monkeypatch.setattr(settings, "WEBHOOK_WORKER_POLL_SECONDS", 0.05)
    stop = asyncio.Event()
    loop = asyncio.create_task(worker.run_worker(stop))
    try:
        for _ in range(200):
            if set((await statuses()).values()) == {"PROCESSED"}:
                break
            await asyncio.sleep(0.05)
    finally:
        stop.set()
        await asyncio.wait_for(loop, 10)
    assert await statuses() == {"evt_restart_1": "PROCESSED", "evt_restart_2": "PROCESSED"}
    assert reconcile.await_count == 2


@pytest.mark.asyncio
async def test_poll_only_returns_stale_queued_rows_oldest_first():
    await queue_events("evt_old", age=timedelta(minutes=10))
    await queue_events("evt_older", age=timedelta(minutes=20))
    await queue_events("evt_fresh")
    async with webhooks.async_session_factory() as db:
        await db.execute(
            update(ProcessedWebhookEvent)
            .where(ProcessedWebhookEvent.razorpay_event_id == "evt_old")
            .values(processing_status="PROCESSED")
        )
        await db.commit()
    await queue_events("evt_oldest", age=timedelta(hours=1))

    assert await worker.queued_event_ids(stale_after=60) == ["evt_oldest", "evt_older"]
    assert await worker.queued_event_ids(stale_after=60, limit=1) == ["evt_oldest"]
    assert len(await worker.queued_event_ids(stale_after=0)) == 3
    async with webhooks.async_session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(ProcessedWebhookEvent)) == 4


@pytest.mark.asyncio
async def test_lock_timeout_leaves_the_event_queued_instead_of_failed(monkeypatch, reconcile):
    await queue_events("evt_locked", age=timedelta(minutes=5))
    busy = OperationalError("BEGIN IMMEDIATE", {}, Exception("database is locked"))
    monkeypatch.setattr(webhooks, "lock_batch", AsyncMock(side_effect=busy))

    assert await webhooks.reconcile_webhook_event("evt_locked") is False
    assert await worker.drain_once(stale_after=60) == 0
    assert await statuses() == {"evt_locked": "QUEUED"}
    reconcile.assert_not_awaited()
