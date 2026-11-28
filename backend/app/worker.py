"""Outbox worker for Razorpay webhook events. Run it with ``python -m app.worker``.

The webhook route commits every accepted settlement and refund event as a QUEUED ProcessedWebhookEvent
before it answers, so that table is the outbox. This loop polls it and hands each event to the same
reconcile_webhook_event the API uses. That function claims the event under the batch lock and checks it
is still QUEUED, so an event is processed once even when the API and several workers race for it.
"""

import asyncio
import contextlib
import signal
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.api.v1 import webhooks
from app.core.config import settings
from app.core.database import engine
from app.core.logging import logger, setup_logging
from app.models.webhook_event import ProcessedWebhookEvent

POLL_BATCH_SIZE = 50


def stale_after_seconds() -> float:
    """How long a QUEUED event is left alone before the worker takes it.

    With the in-process fast path on, the API gets WEBHOOK_STALE_AFTER_SECONDS to finish its own task;
    a row still QUEUED after that was left behind by a crash or restart. With it off, the worker owns
    every queued event straight away.
    """
    if settings.WEBHOOK_INLINE_RECONCILE:
        return float(settings.WEBHOOK_STALE_AFTER_SECONDS)
    return 0.0


async def queued_event_ids(stale_after: float, limit: int = POLL_BATCH_SIZE) -> list[str]:
    """Oldest QUEUED events that were last touched before the stale cutoff.

    On PostgreSQL rows another transaction is reconciling right now are skipped (FOR UPDATE SKIP LOCKED).
    SQLite has no row locks, so there the claim inside reconcile_webhook_event (BEGIN IMMEDIATE plus the
    QUEUED re-check) is what keeps two workers from doing the same event.
    """
    cutoff = datetime.now(UTC) - timedelta(seconds=stale_after)
    async with webhooks.async_session_factory() as db:
        rows = await db.scalars(
            select(ProcessedWebhookEvent.razorpay_event_id)
            .where(
                ProcessedWebhookEvent.processing_status == "QUEUED",
                ProcessedWebhookEvent.updated_at <= cutoff,
            )
            .order_by(ProcessedWebhookEvent.received_at, ProcessedWebhookEvent.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        event_ids = list(rows)
        await db.commit()
    return event_ids


async def drain_once(stale_after: float | None = None, limit: int = POLL_BATCH_SIZE) -> int:
    """Reconcile one page of queued events. Returns how many of them this call processed."""
    if stale_after is None:
        stale_after = stale_after_seconds()
    processed = 0
    for event_id in await queued_event_ids(stale_after, limit):
        try:
            if await webhooks.reconcile_webhook_event(event_id):
                processed += 1
        except Exception:
            # One bad event must not stop the loop; it stays QUEUED or FAILED and the error is logged.
            logger.exception("webhook_worker_event_error", event_id=event_id)
    return processed


async def run_worker(stop: asyncio.Event) -> None:
    """Poll the outbox until stop is set. An event in progress finishes before the loop exits."""
    logger.info(
        "webhook_worker_started",
        inline_reconcile=settings.WEBHOOK_INLINE_RECONCILE,
        stale_after_seconds=stale_after_seconds(),
        poll_seconds=settings.WEBHOOK_WORKER_POLL_SECONDS,
    )
    while not stop.is_set():
        processed = 0
        try:
            processed = await drain_once()
        except Exception:
            logger.exception("webhook_worker_poll_failed")
        if processed:
            logger.info("webhook_worker_processed", count=processed)
            continue  # more may be waiting, poll again right away
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=settings.WEBHOOK_WORKER_POLL_SECONDS)
    logger.info("webhook_worker_stopped")


async def _main() -> None:
    setup_logging()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):  # no signal handlers on Windows event loops
            loop.add_signal_handler(sig, stop.set)
    try:
        await run_worker(stop)
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
