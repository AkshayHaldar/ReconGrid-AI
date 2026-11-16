"""Observability, OpenTelemetry distributed tracing, and Prometheus metrics configuration.

Exposes Prometheus counters, histograms, and OpenTelemetry tracer instrumentation for
reconciliation throughput, tier match distribution, latency profiling, and exception tracking.
"""

from collections.abc import Sequence
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Tracer
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, CollectorRegistry, Counter, Histogram, generate_latest

_HAS_OTEL_SDK = False
try:
    from opentelemetry.sdk.resources import Resource as _Resource
    from opentelemetry.sdk.trace import TracerProvider as _TracerProvider

    _HAS_OTEL_SDK = True
except ImportError:
    pass


def _get_or_create_counter(
    name: str,
    documentation: str,
    labelnames: Sequence[str] = (),
    registry: CollectorRegistry = REGISTRY,
) -> Counter:
    """Idempotently gets or creates a Prometheus Counter to prevent duplicate registration errors."""
    if name in registry._names_to_collectors:
        collector = registry._names_to_collectors[name]
        if isinstance(collector, Counter):
            return collector
    return Counter(name, documentation, labelnames=labelnames, registry=registry)


def _get_or_create_histogram(
    name: str,
    documentation: str,
    labelnames: Sequence[str] = (),
    registry: CollectorRegistry = REGISTRY,
    **kwargs: Any,
) -> Histogram:
    """Idempotently gets or creates a Prometheus Histogram to prevent duplicate registration errors."""
    if name in registry._names_to_collectors:
        collector = registry._names_to_collectors[name]
        if isinstance(collector, Histogram):
            return collector
    return Histogram(name, documentation, labelnames=labelnames, registry=registry, **kwargs)


# Prometheus Metrics as defined in Issue #54:
# 1. recon_total_rows_processed: Total transactions ingested.
recon_total_rows_processed: Counter = _get_or_create_counter(
    name="recon_total_rows_processed",
    documentation="Total transactions ingested and processed during reconciliation.",
)

# 2. recon_matches_total{tier="tier1|tier1_5|tier2|tier3|tier3b"}: Counts per tier.
recon_matches_total: Counter = _get_or_create_counter(
    name="recon_matches_total",
    documentation="Total reconciled matches categorized by matching tier.",
    labelnames=["tier"],
)

# Pre-initialize common tier labels for consistent Prometheus exposition
for _tier_label in ("tier1", "tier1_5", "tier2", "tier3", "tier3b"):
    recon_matches_total.labels(tier=_tier_label)

# 3. recon_exceptions_total: Total unresolved items.
recon_exceptions_total: Counter = _get_or_create_counter(
    name="recon_exceptions_total",
    documentation="Total unresolved reconciliation exception items.",
)

# 4. recon_batch_duration_seconds: Histogram of reconciliation run durations.
recon_batch_duration_seconds: Histogram = _get_or_create_histogram(
    name="recon_batch_duration_seconds",
    documentation="Histogram of reconciliation batch execution durations in seconds.",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)


def setup_telemetry(service_name: str = "recongrid-api") -> Tracer:
    """Initializes OpenTelemetry tracer provider if SDK is present and not yet registered."""
    if _HAS_OTEL_SDK and not isinstance(trace.get_tracer_provider(), _TracerProvider):
        resource = _Resource.create({"service.name": service_name})
        provider = _TracerProvider(resource=resource)
        trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)


tracer: Tracer = trace.get_tracer("recongrid.reconciliation")


def get_latest_metrics() -> bytes:
    """Generates the latest Prometheus exposition metrics format."""
    return generate_latest(REGISTRY)


__all__ = [
    "CONTENT_TYPE_LATEST",
    "get_latest_metrics",
    "recon_batch_duration_seconds",
    "recon_exceptions_total",
    "recon_matches_total",
    "recon_total_rows_processed",
    "setup_telemetry",
    "tracer",
]
