"""Unit and integration tests for OpenTelemetry distributed tracing and Prometheus metrics.

Validates Issue #54 acceptance criteria:
1. Calling GET /metrics returns valid Prometheus exposition text.
2. Reconciling a batch increments recon_total_rows_processed and tier match counters.
3. recon_exceptions_total increments on unresolved items.
4. Optional bearer token and internal network security for /metrics endpoint.
5. Telemetry instrumentation overhead bounds (< 2ms).
"""

import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.telemetry import (
    recon_batch_duration_seconds,
    recon_exceptions_total,
    recon_matches_total,
    recon_total_rows_processed,
    tracer,
)
from app.main import app
from app.repositories.bank_repo import BankRepository
from app.repositories.reconciliation_repo import ReconciliationRepository
from app.repositories.settlement_repo import SettlementRepository
from app.services.reconciliation import ReconciliationEngine


@pytest.mark.asyncio
async def test_metrics_endpoint_exposition_format():
    """Validates that GET /metrics returns valid Prometheus exposition text."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")

        body = response.text
        assert "recon_total_rows_processed" in body
        assert "recon_matches_total" in body
        assert "recon_exceptions_total" in body
        assert "recon_batch_duration_seconds" in body
        assert 'recon_matches_total{tier="tier1"}' in body


@pytest.mark.asyncio
async def test_reconciliation_increments_prometheus_metrics(db_session: AsyncSession):
    """Validates that reconciling a batch correctly increments Prometheus counters per tier and total rows."""
    bank_repo = BankRepository(db_session)
    setl_repo = SettlementRepository(db_session)
    recon_repo = ReconciliationRepository(db_session)
    engine = ReconciliationEngine(recon_repo)

    now = datetime.now(UTC)
    batch_id = "test_telemetry_metrics_batch"

    # Capture baseline metric counts
    base_total = recon_total_rows_processed._value.get()
    base_t1 = recon_matches_total.labels(tier="tier1")._value.get()
    base_t2 = recon_matches_total.labels(tier="tier2")._value.get()
    base_exc = recon_exceptions_total._value.get()
    base_hist_count = next(
        s.value for s in recon_batch_duration_seconds.collect()[0].samples if s.name.endswith("_count")
    )

    # 1. Tier 1 exact match (Amount 50,000, matching UTR)
    tx1, _ = await bank_repo.upsert_transaction(
        {
            "batch_id": batch_id,
            "row_hash": "hash_tel_1",
            "date": now,
            "amount": Decimal("50000.00"),
            "direction": "CREDIT",
            "utr": "CMS0099887711",
            "description": "CMS/CMS0099887711/HDFC SETTLEMENT",
        }
    )
    setl1, _ = await setl_repo.upsert_settlement(
        {
            "settlement_id": "setl_tel_001",
            "amount": Decimal("50000.00"),
            "gross_amount": Decimal("50000.00"),
            "fees": Decimal("0.00"),
            "tax": Decimal("0.00"),
            "utr": "CMS0099887711",
            "status": "processed",
            "settlement_created_at": now,
        }
    )

    # 2. Tier 2 fuzzy match (No UTR on bank side, matching descriptor tokens > 90% threshold)
    tx2, _ = await bank_repo.upsert_transaction(
        {
            "batch_id": batch_id,
            "row_hash": "hash_tel_2",
            "date": now,
            "amount": Decimal("25000.00"),
            "direction": "CREDIT",
            "utr": None,
            "description": "RAZORPAY PAYOUT SETTLEMENT 89213",
        }
    )
    setl2, _ = await setl_repo.upsert_settlement(
        {
            "settlement_id": "setl_tel_002",
            "amount": Decimal("25000.00"),
            "gross_amount": Decimal("25000.00"),
            "fees": Decimal("0.00"),
            "tax": Decimal("0.00"),
            "utr": None,
            "status": "processed",
            "settlement_created_at": now,
            "raw_payload": {"description": "RAZORPAY PAYOUT SETTLEMENT 89214"},
        }
    )

    # 3. Exception (No matching settlement, older than pending window 5 days)
    tx3, _ = await bank_repo.upsert_transaction(
        {
            "batch_id": batch_id,
            "row_hash": "hash_tel_3",
            "date": now - timedelta(days=10),
            "amount": Decimal("11111.00"),
            "direction": "CREDIT",
            "utr": "EXT_DEPOSIT_999",
            "description": "EXTERNAL CLIENT MISC PAYMENT",
        }
    )

    logs = await engine.reconcile_batch([tx1, tx2, tx3], [setl1, setl2], batch_id=batch_id)
    assert len(logs) == 3

    # Assert total rows metric increased by 3
    assert recon_total_rows_processed._value.get() == base_total + 3

    # Assert tier1 match metric increased by 1
    assert recon_matches_total.labels(tier="tier1")._value.get() == base_t1 + 1

    # Assert tier2 match metric increased by 1
    assert recon_matches_total.labels(tier="tier2")._value.get() == base_t2 + 1

    # Assert exception metric increased by 1
    assert recon_exceptions_total._value.get() == base_exc + 1

    # Assert duration histogram recorded batch
    current_hist_count = next(
        s.value for s in recon_batch_duration_seconds.collect()[0].samples if s.name.endswith("_count")
    )
    assert current_hist_count == base_hist_count + 1


@pytest.mark.asyncio
async def test_reconciliation_tier1_5_and_tier3b_metrics(db_session: AsyncSession):
    """Validates that Tier 1.5 substring matches and Tier 3b batched subset sum increment matching counters."""
    bank_repo = BankRepository(db_session)
    setl_repo = SettlementRepository(db_session)
    recon_repo = ReconciliationRepository(db_session)
    engine = ReconciliationEngine(recon_repo)

    now = datetime.now(UTC)
    batch_id = "test_telemetry_t1_5_t3b_batch"

    base_t1_5 = recon_matches_total.labels(tier="tier1_5")._value.get()
    base_t3b = recon_matches_total.labels(tier="tier3b")._value.get()

    # 1. Tier 1.5 Substring match: bank has full NEFT prefix, gateway has raw UTR
    tx_sub, _ = await bank_repo.upsert_transaction(
        {
            "batch_id": batch_id,
            "row_hash": "hash_tel_sub",
            "date": now,
            "amount": Decimal("12000.00"),
            "direction": "CREDIT",
            "utr": "AXISN1234567890",
            "description": "NEFT-AXISN1234567890-MERCHANT",
        }
    )
    setl_sub, _ = await setl_repo.upsert_settlement(
        {
            "settlement_id": "setl_tel_sub",
            "amount": Decimal("12000.00"),
            "gross_amount": Decimal("12000.00"),
            "fees": Decimal("0.00"),
            "tax": Decimal("0.00"),
            "utr": "1234567890",
            "status": "processed",
            "settlement_created_at": now,
        }
    )

    # 2. Tier 3b Batched subset sum (bank receives lump-sum of 20,000 matching two 10,000 settlements)
    tx_batch, _ = await bank_repo.upsert_transaction(
        {
            "batch_id": batch_id,
            "row_hash": "hash_tel_batch",
            "date": now,
            "amount": Decimal("20000.00"),
            "direction": "CREDIT",
            "utr": None,
            "description": "LUMP SUM CONSOLIDATED BATCH",
        }
    )
    setl_b1, _ = await setl_repo.upsert_settlement(
        {
            "settlement_id": "setl_tel_b1",
            "amount": Decimal("10000.00"),
            "gross_amount": Decimal("10000.00"),
            "fees": Decimal("0.00"),
            "tax": Decimal("0.00"),
            "utr": "CMS_B1",
            "status": "processed",
            "settlement_created_at": now,
        }
    )
    setl_b2, _ = await setl_repo.upsert_settlement(
        {
            "settlement_id": "setl_tel_b2",
            "amount": Decimal("10000.00"),
            "gross_amount": Decimal("10000.00"),
            "fees": Decimal("0.00"),
            "tax": Decimal("0.00"),
            "utr": "CMS_B2",
            "status": "processed",
            "settlement_created_at": now,
        }
    )

    logs = await engine.reconcile_batch([tx_sub, tx_batch], [setl_sub, setl_b1, setl_b2], batch_id=batch_id)
    assert len(logs) == 2

    assert recon_matches_total.labels(tier="tier1_5")._value.get() == base_t1_5 + 1
    assert recon_matches_total.labels(tier="tier3b")._value.get() == base_t3b + 1


@pytest.mark.asyncio
async def test_metrics_endpoint_bearer_token_protection():
    """Validates that when METRICS_BEARER_TOKEN is configured, unauthorized access is rejected with 401."""
    original_token = settings.METRICS_BEARER_TOKEN
    try:
        settings.METRICS_BEARER_TOKEN = "super_secret_metrics_token_123"

        transport = ASGITransport(app=app, client=("8.8.8.8", 45000))
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Missing token from external IP -> 401
            resp_no_token = await client.get("/metrics")
            assert resp_no_token.status_code == 401
            assert "Unauthorized metrics access" in resp_no_token.json()["error"]["message"]

            # Invalid token -> 401
            resp_wrong_token = await client.get("/metrics", headers={"Authorization": "Bearer wrong_token"})
            assert resp_wrong_token.status_code == 401

            # Valid token -> 200
            resp_valid_token = await client.get(
                "/metrics", headers={"Authorization": "Bearer super_secret_metrics_token_123"}
            )
            assert resp_valid_token.status_code == 200
            assert "recon_total_rows_processed" in resp_valid_token.text
    finally:
        settings.METRICS_BEARER_TOKEN = original_token


@pytest.mark.asyncio
async def test_metrics_endpoint_internal_network_bypass():
    """Validates that internal loopback and private network IPs can access /metrics without a bearer token."""
    original_token = settings.METRICS_BEARER_TOKEN
    try:
        settings.METRICS_BEARER_TOKEN = "require_token_unless_internal"

        # Loopback IP (127.0.0.1)
        transport_internal = ASGITransport(app=app, client=("127.0.0.1", 54321))
        async with AsyncClient(transport=transport_internal, base_url="http://test") as client:
            resp = await client.get("/metrics")
            assert resp.status_code == 200
            assert "recon_total_rows_processed" in resp.text
    finally:
        settings.METRICS_BEARER_TOKEN = original_token


def test_telemetry_span_overhead_bound():
    """Validates Acceptance Criteria #3: Telemetry instrumentation introduces < 2ms overhead."""
    # Measure execution of OpenTelemetry span context manager
    n_iterations = 200
    t0 = time.perf_counter()
    for _ in range(n_iterations):
        with tracer.start_as_current_span("recon.tier1_exact_match"):
            pass
    t_elapsed = time.perf_counter() - t0
    avg_per_span_ms = (t_elapsed / n_iterations) * 1000.0

    # Each span must be under 0.05ms (50 microseconds)
    assert avg_per_span_ms < 0.05, f"Span overhead {avg_per_span_ms:.4f}ms exceeded limit"
    # Total overhead for 200 spans is well below 2ms
    assert (t_elapsed * 1000.0) < 2.0, f"Total overhead {t_elapsed * 1000.0:.2f}ms exceeded 2ms"
