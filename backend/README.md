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
│   └── utils/
│       ├── csv_parser.py   # Dialect sniffing, preamble skip, UTR extraction
│       ├── fuzzy.py        # Levenshtein distance & token sort ratios
│       ├── money.py        # Decimal money arithmetic and INR currency formatters
│       └── pdf_parser.py   # Encrypted PDF text & table extractor
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

---

## 4. Testing & Verification

All tests can be executed directly with `pytest`:

```bash
# 1. Quick sanity test (matching engine unit test, runs in < 1 second)
pytest tests/unit/test_reconciliation_engine_edges.py -v

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

# Export balanced Tally Prime XML journal vouchers
curl -X GET "http://localhost:8000/api/v1/reconciliation/default/tally-export" -o recongrid_tally.xml
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
