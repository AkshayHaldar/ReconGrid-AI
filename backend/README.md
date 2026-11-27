# ReconGrid AI — Backend Engine

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-brightgreen.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-teal.svg)](https://fastapi.tiangolo.com)
[![SQLAlchemy 2.0](https://img.shields.io/badge/SQLAlchemy-2.0-red.svg)](https://docs.sqlalchemy.org)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2-e92063.svg)](https://docs.pydantic.dev)
[![Alembic](https://img.shields.io/badge/Alembic-Migrations-red.svg)](https://alembic.sqlalchemy.org)
[![Tests Passing](https://img.shields.io/badge/pytest-Passing-brightgreen.svg)](./tests)

[← Back to Main Repository](../README.md) • [Architecture Guide](../ARCHITECTURE.md) • [System Design](../SYSTEM-DESIGN.md) • [Contributing](../CONTRIBUTING.md)

---

## 1. Overview

The `backend` directory contains the core reconciliation engine, ingestion parsers, and financial ledger services for ReconGrid AI.

It is built as an asynchronous **FastAPI** application with **SQLAlchemy 2.0** and **Pydantic v2**, backed by SQLite for zero-config local development and PostgreSQL 15 for production.

### Core Architectural Guarantees:
1. **Zero Floating-Point Math:** All financial values use Python standard library `Decimal(18, 2)` with explicit rounding (`ROUND_HALF_UP`). Floats are rejected at the Pydantic schema boundary.
2. **Deterministic Matching Core:** Reconciliation decisions are made entirely by deterministic rules (UTRs, normalized entropy, fuzzy strings, date windows, fee formulas). No LLM is in the critical decision path.
3. **Guardrailed Natural Language:** The Settlement Q&A Agent uses LLMs (NVIDIA NIM / LLaMA 3.3 70B) strictly for read-only explanation. Every numeric token is cross-checked against database records by a regex guardrail.
4. **Append-Only Auditing:** Records are marked `superseded=True`, never physically deleted.

---

## 2. Directory Layout

```
backend/
├── alembic/                # Database migration scripts
│   └── versions/           # Versioned migration files
├── app/
│   ├── api/v1/             # HTTP route controllers
│   │   ├── bank.py         # Bank statement upload (CSV/PDF) and password hints
│   │   ├── demo.py         # Synthetic batch seeding and database reset
│   │   ├── qa.py           # Settlement Q&A query endpoints
│   │   ├── razorpay.py     # Razorpay API sync and stored settlement retrieval
│   │   ├── reconciliation.py # Ledger query, approvals, and conflict resolution
│   │   └── webhooks.py     # HMAC-verified real-time Razorpay webhooks
│   ├── core/
│   │   ├── config.py       # Pydantic Settings management (.env)
│   │   ├── database.py     # Async engine & session factory (SQLite / PostgreSQL)
│   │   ├── locks.py        # Per-batch write lock (advisory lock / BEGIN IMMEDIATE)
│   │   └── logging.py      # Structured JSON logging with structlog
│   ├── models/             # SQLAlchemy async ORM models
│   │   ├── bank_transaction.py
│   │   ├── qa_interaction_log.py
│   │   ├── razorpay_settlement.py
│   │   ├── reconciliation_log.py
│   │   └── webhook_event.py
│   ├── schemas/            # Pydantic v2 schemas (with strict float rejection)
│   ├── services/           # Core domain logic
│   │   ├── diagnostics.py  # Fee formulas (2% MDR + 18% GST, 1% TDS, refunds)
│   │   ├── guardrail.py    # Regex-based anti-hallucination number validator
│   │   ├── ingestion.py    # Statement normalizer & deduplication service
│   │   ├── razorpay_client.py # Async HTTP client with cursor pagination & backoff
│   │   ├── reconciliation.py # 4-tier matching engine & subset-sum scan
│   │   ├── settlement_qa.py  # LLM narration with fact retrieval
│   │   └── tally_export.py   # Accounting ERP XML export generator
│   ├── utils/
│   │   ├── csv_parser.py   # Dialect sniffing, preamble skip, UTR extraction
│   │   ├── fuzzy.py        # Levenshtein distance & token sort ratios
│   │   ├── money.py        # Decimal money arithmetic and INR currency formatters
│   │   └── pdf_parser.py   # Encrypted PDF text & table extractor
│   └── worker.py           # Webhook outbox worker (python -m app.worker)
├── scripts/                # Benchmarking and synthetic data generators
│   ├── benchmark_throughput.py
│   ├── generate_scorecard_report.py
│   └── seed_demo_data.py
├── tests/                  # Test suites
│   ├── integration/        # Synthetic batch, messy fixtures, and end-to-end flows
│   └── unit/               # Float rejection, schema validation, parser tests
├── alembic.ini             # Alembic configuration
├── pyproject.toml          # Project metadata, dependencies, ruff & mypy configs
└── requirements.txt        # Pinned requirements
```

---

## 3. Local Development Setup

### 1. Create and Activate Virtual Environment

From the `backend/` directory:

```bash
python -m venv .venv
```

* **Windows (PowerShell):**
  ```powershell
  .venv\Scripts\Activate.ps1
  ```
* **macOS / Linux:**
  ```bash
  source .venv/bin/activate
  ```

### 2. Install Dependencies

```bash
pip install -e ".[dev]"
```

### 3. Initialize Database

Copy the default environment configuration (configured for local SQLite by default):

```bash
# Windows: copy .env.example .env
# macOS/Linux: cp .env.example .env
cp .env.example .env

# Apply migrations
alembic upgrade head
```

### 4. Run the API Server

```bash
uvicorn app.main:app --reload --port 8000
```

Open **[http://localhost:8000/docs](http://localhost:8000/docs)** for interactive Swagger API testing.

### 5. Run the Webhook Worker

In a second terminal (same virtual environment and `.env`):

```bash
python -m app.worker
```

It reconciles webhook events that are still `QUEUED`; see [Webhook acknowledgement and background work](#webhook-acknowledgement-and-background-work). Stop it with Ctrl+C or SIGTERM; an event in progress finishes first.

---

## 4. Testing & Verification

All tests can be executed directly with `pytest`:

```bash
# 1. Quick sanity test (diagnostics unit test, runs in < 1 second)
pytest tests/unit/test_diagnostics.py -v

# 2. Verify schema-level float rejection (Zero-Float Policy)
pytest tests/unit/test_schema_float_rejection.py -v

# 3. Test messy Indian bank statement fixtures (SBI, HDFC, ICICI, Axis)
pytest tests/integration/test_messy_fixtures_e2e.py -v

# 4. Run the 50+ record synthetic batch integration test
pytest tests/integration/test_synthetic_batch.py -v

# 5. Run full test suite with line-by-line coverage
pytest --cov=app --cov-report=term-missing

# 6. Run linting and static type checking
ruff check .
mypy app
```

---

## 5. Running Throughput Benchmarks

ReconGrid AI includes an end-to-end benchmark script that creates synthetic transaction batches, executes multi-tier matching, persists results to the database, and measures throughput:

```bash
python scripts/benchmark_throughput.py
```

### Measured Benchmark Results:
| Batch Size | Time | Throughput | Peak RAM | Match Rate | Unresolved Anomalies | Conservation |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **50** | `0.035s` | **1,424 rows/s** | 1.5 MB | 96.0% | 2 (₹ 99,998.00) | 100% (0 lost) |
| **200** | `0.108s` | **1,855 rows/s** | 2.7 MB | 95.0% | 10 (₹ 499,990.00) | 100% (0 lost) |
| **500** | `0.314s` | **1,594 rows/s** | 6.5 MB | 94.8% | 9 (₹ 449,991.00) | 100% (0 lost) |
| **1,000** | `0.972s` | **1,029 rows/s** | 12.9 MB | 94.8% | 17 (₹ 849,983.00) | 100% (0 lost) |

---

## 6. Zero-Float Policy (How It Works)

Python's standard `float` type uses binary IEEE 754 representations, leading to precision errors in currency calculations:

```python
>>> 100.00 - (100.00 * 0.02) - (100.00 * 0.02 * 0.18)
97.64
>>> float(0.1) + float(0.2)
0.30000000000000004
```

In ReconGrid:
- All monetary fields in `app/schemas/` are typed as `Decimal`.
- Custom Pydantic validators reject raw floats: passing `{"amount": 100.5}` triggers an immediate `ValidationError`. Payloads must supply integers, string representations (`"100.50"`), or paise.
- All calculations in `app/services/diagnostics.py` use `ROUND_HALF_UP` with 2 decimal places.

---

## 7. Useful Terminal (cURL) Commands

```bash
# Seed 60 synthetic records with exact matches, fee deltas, and anomalies
curl -X POST "http://localhost:8000/api/v1/demo/seed?count=60&batch_id=default"

# Get reconciliation summary metrics
curl -X GET "http://localhost:8000/api/v1/reconciliation/default/status"

# Fetch audit scorecard with per-tier breakdown
curl -X GET "http://localhost:8000/api/v1/reconciliation/default/scorecard"

# Ask the Settlement Q&A Agent
curl -X POST "http://localhost:8000/api/v1/qa/ask" \
  -H "Content-Type: application/json" \
  -d '{"query": "Why did order 4521 settle with a delta?", "history": []}'

# Export the reconciled audit ledger as CSV
curl -X GET "http://localhost:8000/api/v1/reconciliation/default/export" -o recongrid_audit.csv
```

---

## 8. Database Migrations (Alembic)

When modifying SQLAlchemy models in `app/models/`:

```bash
# Create an autogenerated migration
alembic revision --autogenerate -m "add index on utr"

# Apply pending migrations
alembic upgrade head

# Roll back the most recent migration
alembic downgrade -1
```

### Webhook acknowledgement and background work

`POST /api/v1/webhooks/razorpay` verifies the HMAC and commits a deduplicated event before responding. Settlement events return HTTP 200 with `data.status = "queued"`, the event ID and `action_taken = "RECONCILIATION_QUEUED"` in the existing API envelope. Settlement upsert and reconciliation then run in a FastAPI background task with its own database session (unless `WEBHOOK_INLINE_RECONCILE=false`, see below); the request session is never passed to the worker. Unsupported events are recorded without scheduling reconciliation.

The stored event status progresses from `QUEUED` to `PROCESSED`. A worker exception rolls back settlement/reconciliation writes, logs `webhook_reconciliation_failed` with the event ID, and records `FAILED`. A redelivery of that same signed event can atomically requeue a failed attempt. Completed or already queued duplicate deliveries are acknowledged without creating another task.

#### Outbox worker and crash recovery

The `QUEUED` row is the outbox entry: it is committed before the provider gets HTTP 200, so it survives an API crash or restart. `python -m app.worker` (the `worker` service in `docker-compose.yml`) polls `processed_webhook_events` and hands each `QUEUED` event to the same `reconcile_webhook_event` the API uses. That call claims the event inside one transaction: it takes the batch lock, re-reads the row only if it is still `QUEUED` (`FOR UPDATE SKIP LOCKED` on PostgreSQL), upserts the settlement, reconciles and marks it `PROCESSED`. There is no separate in-progress status. A crash or kill mid reconcile rolls the whole attempt back, so the row is simply `QUEUED` again, and two callers racing for the same event (API task and worker, or two workers) end with one reconciliation and one no-op.

| Setting | Default | Meaning |
|---|---|---|
| `WEBHOOK_INLINE_RECONCILE` | `true` | `true`: the API still reconciles right after acknowledging (FastAPI background task) and the worker only takes events still `QUEUED` after `WEBHOOK_STALE_AFTER_SECONDS`. `false`: the API only enqueues and the worker reconciles every event on its next poll. `docker-compose.yml` sets `false`. |
| `WEBHOOK_STALE_AFTER_SECONDS` | `60` | How long, measured from the row's `updated_at`, a `QUEUED` event belongs to the in-process task before the worker recovers it. Ignored when inline reconcile is off. |
| `WEBHOOK_WORKER_POLL_SECONDS` | `5` | Sleep between polls when the outbox is empty. |

Without a running worker, inline reconcile still works as before, but an event left `QUEUED` by a crash waits until a worker starts. `FAILED` events are not retried by the worker; a redelivery requeues them as before. The provider has already received HTTP 200, so do not rely on it automatically retrying a later background failure. No production latency guarantee is implied by local tests. The worker does not use Redis yet: the outbox is the PostgreSQL table, so no extra dependency is needed.

#### Per-batch write lock

Every path that rewrites a batch's reconciliation snapshot takes the same lock first, through `app.core.locks.lock_batch`: the webhook reconcile (batch `default`), `POST /bank/upload` (before its first insert), `POST /razorpay/sync` (after the network fetch, before its first write) and the human mutations (`records/{id}/approve`, `deny`, `revert`, `resolve-conflict` and `{batch_id}/batch-approve`). On PostgreSQL it is `pg_advisory_xact_lock(1380405828, <32-bit key from sha256(batch_id)>)`, so writers of the same batch queue up while other batches are not blocked. SQLite uses `BEGIN IMMEDIATE` before the reads; it has a single writer per database, so there every batch shares the lock and queued work can delay another write. The lock is released on commit/rollback. This keeps a webhook, an upload, a sync or a review action from committing an older snapshot over a newer one. Production latency must be measured with the intended database.

A `settlement.processed` event without a nonempty settlement entity is rejected before an event is recorded, allowing a corrected redelivery. If a provider settlement ID is absent, the fallback uses `setl_` plus a 59-character event-ID digest, keeping the identifier within its 64-character column without truncating common event-ID prefixes.
