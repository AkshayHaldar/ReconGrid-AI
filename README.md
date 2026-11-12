# ReconGrid AI

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-brightgreen.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-teal.svg)](https://fastapi.tiangolo.com)
[![Next.js 14](https://img.shields.io/badge/Next.js-14.2-black.svg)](https://nextjs.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-316192.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![Alembic](https://img.shields.io/badge/Alembic-Migrations-red.svg)](https://alembic.sqlalchemy.org)
[![Backend CI](https://github.com/AkshayHaldar/ReconGrid-AI/actions/workflows/backend-ci.yml/badge.svg)](https://github.com/AkshayHaldar/ReconGrid-AI/actions/workflows/backend-ci.yml)
[![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-green.svg)](./CONTRIBUTING.md)

An open-source settlement reconciliation and discrepancy diagnostic engine with an audited Q&A agent for Razorpay merchants and finance teams.

Originally built for the **Razorpay Buildathon 2026 (Track 04: AI Finance Controller)**, ReconGrid AI automates the painful process of matching bank statements against Razorpay payment gateway settlements.

---

## Reconciliation in 60 Seconds (Why This Exists)

If you have never worked in fintech or accounting, here is the problem in plain terms:

Suppose a customer buys a **₹10,000.00** product on your website through Razorpay. You might expect your bank account to show a credit of ₹10,000.00. It never does.

Instead, your bank statement shows a credit of **₹9,664.00**:

```
 Gross customer payment:                    ₹ 10,000.00
  - Gateway fee (2.0% MDR):                 -   ₹ 200.00
  - 18% GST on that fee (18% of ₹200):      -    ₹ 36.00
  - E-commerce TDS (Section 194-O, 1%):     -   ₹ 100.00
────────────────────────────────────────────────────────
 Net amount credited to your bank:           ₹ 9,664.00
```

Now multiply that by 5,000 transactions a month. Add in:
* **Batched payouts:** Razorpay combines 40 customer payments into one single lump-sum bank deposit.
* **Mid-cycle refunds:** A ₹1,500 customer refund is deducted from tomorrow's settlement batch.
* **Messy bank exports:** HDFC, SBI, ICICI, and Axis export CSVs and PDFs with non-standard columns, encrypted passwords, and UTRs (Unique Transaction References) buried inside 80-character narration text.

Chartered Accountants (CAs) and finance leads spend 20 to 40 hours every month manually cross-referencing Excel sheets with `VLOOKUP` to find out where missing rupees went.

### The ReconGrid Solution: Deterministic Math + Guardrailed AI

ReconGrid AI enforces a strict architectural boundary:
1. **100% Deterministic Code for Money:** All matching, fee deductions, tax calculations, and ledger balances run in pure Python using `Decimal` (zero floating-point math). AI never touches, calculates, or decides financial amounts.
2. **AI Only for Plain-English Explanation:** An LLM is used strictly to answer user questions about pre-computed audit facts (e.g., *"Why did order #4521 have a ₹336 delta?"*).
3. **Regex Numeric Guardrail:** An anti-hallucination check compares every number in the LLM's answer against the database record. If the LLM invents or alters any number, its text is immediately discarded and replaced with raw database facts.

---

## Key Terms (Fintech Primer)

If you are new to Indian banking and payment gateways, here are the terms used throughout this codebase and documentation:

| Term | What It Means | Why It Matters Here |
|---|---|---|
| **UTR** | *Unique Transaction Reference* | The 12-to-22 character alphanumeric ID assigned by the banking system (NEFT / RTGS / IMPS) to identify a money transfer. This is our primary key for matching bank rows to gateway settlements. |
| **MDR** | *Merchant Discount Rate* | The fee Razorpay charges per transaction (typically ~2%). |
| **GST on MDR** | *18% Goods and Services Tax* | Indian tax applied strictly to the gateway fee (e.g., 18% of ₹200 fee = ₹36 GST). |
| **Section 194-O TDS** | *Tax Deducted at Source* | Under Indian income tax law, e-commerce operators must withhold 1% tax on gross sales. |
| **Paise vs. Rupee** | $1\text{ INR} = 100\text{ paise}$ | Razorpay APIs handle money in integer paise (`₹100.00` = `10000` paise) to avoid decimal errors. Bank statements report in rupees. Ingestion normalizes everything to Python `Decimal(18, 2)` rupees. |
| **Conservation** | Mathematical balance guarantee | $\sum(\text{matched} + \text{suggested} + \text{conflicts} + \text{exceptions} + \text{pending}) = \text{total ingested}$. Zero dropped rows, zero ghost rupees. |

---

## Razorpay Hackathon Track 04: AI Finance Controller

ReconGrid AI was built specifically to address the mandate of Track 04:

> *"Build finance-ops agents that close the loop over synthetic data with 50+ record batches, reporting match rates and unresolved anomalies... Verification capacity, not generation speed, is the bottleneck."*

### Track 04 Requirements vs Implementation

| Hackathon Requirement | How ReconGrid AI Implements It | Verification |
|---|---|---|
| **50+ Record Batch Processing** | Deterministic multi-tier matcher with indexed UTR lookup and batched DB persistence. | `python backend/scripts/benchmark_throughput.py`<br>Processes 50 rows in **0.035s** (~1,424 rows/s); 1,000 rows in **0.97s**. |
| **Tiered Match Rates** | Clear classification into Tier 1 (exact UTR), Tier 1.5 (normalized UTR), Tier 2 (fuzzy narration), Tier 0 (date window fallback), and Tier 3 (fee/tax delta diagnostics). | `GET /api/v1/reconciliation/{batch_id}/scorecard`<br>Reports exact per-tier counts rather than an opaque single percentage. |
| **Honest Anomaly Reporting** | Zero-silent-drop policy. Unmatched transactions remain unresolved with specific diagnostic reason codes (`UNRESOLVED`, `FEE_DEDUCTION`, `REFUND_ADJUSTED`, `TDS_194O_DEDUCTION`, `PENDING_SETTLEMENT`). | `python backend/scripts/generate_scorecard_report.py`<br>Outputs the complete unedited exception ledger. |
| **Closed-Loop Controller** | Move beyond read-only views: CA can approve suggested matches, reject false positives, and resolve multi-row conflicts with automated competitor displacement. | `POST /api/v1/reconciliation/records/{id}/approve`<br>`POST /api/v1/reconciliation/records/{id}/resolve-conflict` |
| **Zero-Float Conservation** | End-to-end Python `Decimal(18, 2)` arithmetic with schema-level rejection of IEEE 754 floats. Mathematical row conservation guaranteed: $\sum(\text{all tiers} + \text{conflicts} + \text{exceptions} + \text{pending}) = \text{total ingested}$. | `pytest backend/tests/unit/test_schema_float_rejection.py` |

### Throughput Benchmarks

Measured on standard hardware with full DB writes and audit logging:

| Batch Size | Time | Throughput | Peak RAM | Match Rate | Unresolved Anomalies | Conservation |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **50** | 0.035s | 1,424 rows/s | 1.5 MB | 96.0% | 2 (₹ 99,998.00) | 100% (0 lost) |
| **200** | 0.108s | 1,855 rows/s | 2.7 MB | 95.0% | 10 (₹ 499,990.00) | 100% (0 lost) |
| **500** | 0.314s | 1,594 rows/s | 6.5 MB | 94.8% | 9 (₹ 449,991.00) | 100% (0 lost) |
| **1,000** | 0.972s | 1,029 rows/s | 12.9 MB | 94.8% | 17 (₹ 849,983.00) | 100% (0 lost) |
| **5,000** | 32.63s | 153 rows/s | 67.5 MB | 94.7% | 13 (₹ 649,987.00) | 100% (0 lost) |

---

## How It Works

```
Bank Statements (CSV / PDF)             Razorpay Gateway (API / Webhooks)
           │                                           │
           ▼                                           ▼
┌─────────────────────────────┐             ┌─────────────────────────────┐
│ Ingestion & Normalization   │             │ Gateway Sync & Webhooks     │
│ • Skip bank preambles (SBI) │             │ • HMAC signature check      │
│ • Clean ₹ and lakh commas   │             │ • Cursor pagination         │
│ • Extract embedded UTRs     │             │ • Net = Gross - Fees - Tax  │
└──────────────┬──────────────┘             └──────────────┬──────────────┘
               │                                           │
               └─────────────────────┬─────────────────────┘
                                     ▼
                   ┌───────────────────────────────────┐
                   │ Deterministic Multi-Tier Matcher  │
                   │ • Tier 1:   Exact UTR + Amount    │
                   │ • Tier 1.5: Normalized UTR        │
                   │ • Tier 2:   Fuzzy Narration (90%) │
                   │ • Tier 0:   Date Fallback (+/-3d) │
                   │ • Tier 3:   Delta Diagnostics     │
                   └─────────────────┬─────────────────┘
                                     │
                     ┌───────────────┴───────────────┐
                     ▼                               ▼
       ┌───────────────────────────┐   ┌───────────────────────────┐
       │ Append-Only Audit Ledger  │   │ Settlement Q&A Agent      │
       │ • Matched / Suggested     │   │ • Reads computed DB facts │
       │ • Conflict lock           │   │ • Plain-English summary   │
       │ • 1-click CA approval     │   │ • Regex guardrail checks  │
       │ • CSV export              │   │   every number mentioned  │
       └───────────────────────────┘   └───────────────────────────┘
```

### The Multi-Tier Matching Engine

1. **Tier 1 (Exact Match — 100%):** Bank UTR matches Razorpay UTR exactly and the net amount matches. Automatically marked `MATCHED`.
2. **Tier 1.5 (Normalized UTR — 98%):** UTR match after stripping bank-specific prefix/suffix tokens. Marked `SUGGESTED`.
3. **Tier 2 (Fuzzy Descriptor — $\ge 90\%$):** Levenshtein token similarity on narrations. Marked `SUGGESTED` for human review.
4. **Tier 0 (Date Window Fallback):** For rows missing UTRs, matches on amount within a $\pm 3$ day settlement window. Marked `SUGGESTED`.
5. **Tier 3 (Diagnostic Deltas & Subset-Sum):** Explains differences due to MDR fees, 18% GST, Section 194-O TDS, refunds, or batched payouts.
6. **Conflict Resolution:** When multiple bank transactions claim the same Razorpay settlement, both are locked in `CONFLICT`. A human CA can assign the settlement to the correct row with one click, which automatically moves the competing row to `EXCEPTION`.

### Guardrailed AI Q&A Agent

Users can ask questions like:
> *"Why did order #4521 settle with a ₹23.60 difference?"*

- The backend fetches the pre-computed audit record from PostgreSQL/SQLite.
- An LLM (via NVIDIA NIM / LLaMA 3.3 70B) generates a plain-English explanation.
- An anti-hallucination regex guardrail checks all numbers in the LLM response against the DB record. If any number was invented, the LLM response is discarded and replaced with raw database facts.

---

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), Alembic (migrations)
- **Database:** SQLite with `aiosqlite` (local dev/testing) / PostgreSQL 15 with `asyncpg` (production & Docker)
- **Frontend:** Next.js 14 (App Router), TypeScript, Tailwind CSS, Lucide icons
- **Cache & Services:** Redis 7, Docker & Docker Compose
- **Payment Gateway:** Razorpay REST API (settlements, payments, refunds, HMAC-SHA256 webhooks)
- **AI / LLM:** NVIDIA NIM (LLaMA 3.3 70B) for read-only explanations with strict regex guardrail

---

## Quickstart (Get Running in 3 Minutes)

You do **not** need live Razorpay credentials or bank files to test ReconGrid. The system includes a built-in synthetic test data generator that seeds realistic bank statement rows and Razorpay settlements across all match tiers.

### Prerequisites
- **Python:** 3.11 or newer
- **Node.js:** 18 or newer
- **Git**
- *(Optional)* Docker & Docker Compose if you want PostgreSQL + Redis locally

---

### Step 1: Clone the Repository
```bash
git clone https://github.com/AkshayHaldar/ReconGrid-AI.git
cd ReconGrid-AI
```

---

### Step 2: Set Up the Backend

Open a terminal in the `backend/` directory:

```bash
cd backend
python -m venv .venv
```

**Activate your virtual environment:**
* **Windows (PowerShell):**
  ```powershell
  .venv\Scripts\Activate.ps1
  ```
  *(If PowerShell blocks scripts, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first)*
* **macOS / Linux (bash/zsh):**
  ```bash
  source .venv/bin/activate
  ```

**Install dependencies & prepare database:**
```bash
pip install -r requirements.txt

# Create your local environment file (defaults to zero-config SQLite)
# On Windows: copy .env.example .env
# On macOS/Linux: cp .env.example .env
cp .env.example .env

# Apply database migrations
alembic upgrade head

# Start the API server
uvicorn app.main:app --reload --port 8000
```

> **Database Note:** By default, `.env` runs on SQLite (`sqlite+aiosqlite:///./recongrid.db`) with zero setup. If you prefer PostgreSQL, set `DATABASE_URL=postgresql+asyncpg://recongrid:recongrid@localhost:5432/recongrid` and run `alembic upgrade head`.

Your interactive Swagger documentation will be live at: **[http://localhost:8000/docs](http://localhost:8000/docs)**.

---

### Step 3: Set Up the Frontend

Open a second terminal in the `frontend/` directory:

```bash
cd frontend
npm install
npm run dev
```

Open your browser to: **[http://localhost:3000](http://localhost:3000)**.

---

### Step 4: Seed Demo Data (See It in Action Immediately)

With both servers running, open a third terminal and run:

```bash
# Seed 60 synthetic records with exact matches, fee deltas, refunds, and anomalies:
curl -X POST "http://localhost:8000/api/v1/demo/seed?count=60&batch_id=default"
```

Refresh **[http://localhost:3000](http://localhost:3000)**. You will see:
- Real-time match rate calculations (~95-96%)
- Categorized status badges (`MATCHED`, `SUGGESTED`, `CONFLICT`, `EXCEPTION`)
- The interactive CA approval drawer for human-in-the-loop verification
- The Settlement Q&A panel ready for plain-English financial queries

---

### Alternative: Run Everything with Docker Compose

If you have Docker installed and prefer running PostgreSQL 15, Redis 7, Backend, and Frontend in containers:

```bash
docker compose up --build -d
```
- **Frontend Dashboard:** [http://localhost:3000](http://localhost:3000)
- **FastAPI OpenAPI Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **PostgreSQL:** Port `5432` (credentials: `recongrid`/`recongrid`)
- **Redis:** Port `6379`

---

## Testing & Verification

Run the test suite from the `backend/` directory:

```bash
cd backend

# Run all tests
pytest -v

# Run the 50+ record synthetic batch test
pytest tests/integration/test_synthetic_batch.py -v

# Run messy bank statement fixture tests
pytest tests/integration/test_messy_fixtures_e2e.py -v

# Run zero-float schema validation test
pytest tests/unit/test_schema_float_rejection.py -v

# Run throughput benchmark
python scripts/benchmark_throughput.py

# Linting & Formatting checks (CI parity)
ruff check .
ruff format --check .

# Static type checking
mypy app
```

### Generating Test Coverage Locally
Backend test coverage is measured using `pytest-cov` targeting the `app` package:

```bash
cd backend
pip install -e ".[dev]"
pytest --cov=app --cov-report=term-missing --cov-report=xml:coverage.xml --cov-report=html:htmlcov
```

Open `backend/htmlcov/index.html` in a browser to inspect line-by-line coverage locally. In CI, coverage summaries are published directly to the **GitHub Actions Job Summary** and downloadable via the `backend-coverage-report` workflow artifact.

### Required CI Checks
All pull requests targeting `main` must pass the following 10 required status checks before merging:

- Backend pytest
- Ruff
- mypy
- Frontend typecheck
- Frontend lint
- Frontend production build
- Security audit
- Backend Docker build
- Frontend Docker build
- PostgreSQL integration tests

---

## Testing via cURL

You can test the entire workflow from the terminal:

```bash
# 1. Seed a 60-record synthetic batch covering all tiers
curl -X POST "http://localhost:8000/api/v1/demo/seed?count=60&batch_id=default"

# 2. Get batch status and match rate
curl -X GET "http://localhost:8000/api/v1/reconciliation/default/status"

# 3. Get audit scorecard with per-tier breakdown
curl -X GET "http://localhost:8000/api/v1/reconciliation/default/scorecard"

# 4. Ask the Settlement Q&A Agent
curl -X POST "http://localhost:8000/api/v1/qa/ask" \
  -H "Content-Type: application/json" \
  -d '{"query": "Why did order 4521 settle with a delta?", "history": []}'

# 5. Fetch records needing CA review
curl -X GET "http://localhost:8000/api/v1/reconciliation/default/records?status=SUGGESTED"

# 6. One-click approve a suggested match
curl -X POST "http://localhost:8000/api/v1/reconciliation/records/<RECORD_ID>/approve" \
  -H "Content-Type: application/json" \
  -d '{"note": "Approved by CA"}'

# 7. Download complete audit ledger CSV
curl -X GET "http://localhost:8000/api/v1/reconciliation/default/export" \
  -o recongrid_audit.csv
```

---

## API Endpoints

All routes are under `/api/v1`:

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/bank/upload` | Upload CSV/PDF bank statement (supports password-protected PDFs) |
| `GET` | `/bank/transactions` | List ingested bank statement rows |
| `GET` | `/bank/password-hints` | Bank PDF password formats (SBI, HDFC, ICICI, Axis) |
| `POST` | `/razorpay/sync` | Trigger settlement pull from Razorpay REST API |
| `GET` | `/razorpay/settlements` | List stored settlements |
| `POST` | `/webhooks/razorpay` | Ingest real-time webhooks (HMAC-SHA256 verified) |
| `GET` | `/reconciliation/{batch_id}/status` | Summary metrics (match rate, ₹ reconciled) |
| `GET` | `/reconciliation/{batch_id}/scorecard` | Audit scorecard with separate Tier 0/1/1.5/2/3 breakdown |
| `GET` | `/reconciliation/{batch_id}/records` | Paginated records filtered by status or diagnostic code |
| `POST` | `/reconciliation/records/{id}/approve` | Approve a suggested match |
| `POST` | `/reconciliation/records/{id}/deny` | Move suggested match to unresolved exception |
| `POST` | `/reconciliation/records/{id}/resolve-conflict` | Assign settlement and displace competing rows |
| `GET` | `/reconciliation/{batch_id}/export` | Export audit ledger as CSV |
| `POST` | `/qa/ask` | Ask question to the Settlement Q&A Agent |
| `GET` | `/qa/history` | View Q&A query history |
| `POST` | `/demo/seed` | Seed test batch |
| `POST` | `/demo/reset` | Clear test records |

---

## Open Source & Contributing

We are opening this project up to the community to make it the standard open-source reconciliation engine for businesses, developers, and finance teams.

If you want to contribute, please check [CONTRIBUTING.md](./CONTRIBUTING.md).

### Roadmap & Ideas to Work On

- **Bank Statement Parsers:** Add parser dialects for more Indian and international banks (Kotak, Punjab National Bank, Bank of Baroda, Federal Bank, Canara Bank).
- **Payment Gateway Adapters:** Add modular connectors for Stripe, Cashfree, PayU, and Pine Labs following the `RazorpayClient` pattern.
- **Accounting ERP Exports:** Direct export to Tally Prime XML, Zoho Books, or QuickBooks.
- **Local LLM Support:** Add Ollama or vLLM backends for running the Q&A Agent entirely offline.
- **Frontend Enhancements:** Add keyboard shortcuts (`A` to approve, `D` to deny), custom date filters, and dark mode toggles.

### Core Development Rules

1. **Zero-Float Policy:** Never use `float` for currency. Always use Python `Decimal` with explicit rounding (`ROUND_HALF_UP`).
2. **Deterministic Financial Math:** The AI must never perform reconciliation matching or calculations. Financial decisions stay in deterministic code.
3. **Guardrailed Output:** Any LLM explanation must be verified by `app/services/guardrail.py` to ensure zero hallucinated numbers.

---

## Project Structure

```
ReconGrid-AI/
├── .github/
│   └── workflows/          # GitHub Actions (Backend CI, Frontend CI, Docker & Trivy scan)
├── backend/
│   ├── alembic/            # Database schema migration versions
│   │   └── versions/
│   ├── app/
│   │   ├── api/v1/         # Route handlers (bank, razorpay, reconciliation, qa, webhooks)
│   │   ├── core/           # Config, database engine, security (HMAC), logging
│   │   ├── models/         # SQLAlchemy async models
│   │   ├── schemas/        # Pydantic v2 validation models
│   │   ├── services/       # Ingestion, matching engine, diagnostics, Q&A agent
│   │   └── utils/          # Decimal money helpers, CSV streaming, fuzzy string logic
│   ├── scripts/            # Benchmarks, synthetic data seeder, scorecard CLI
│   ├── tests/              # Unit, integration, and messy fixture test suites
│   ├── alembic.ini         # Alembic migration configuration
│   ├── Dockerfile          # Backend container image definition
│   └── requirements.txt    # Production & dev dependencies
├── frontend/
│   ├── src/
│   │   ├── app/            # Next.js App Router (dashboard page and layout)
│   │   ├── components/     # Table, drawers, summary cards, Q&A slide-out
│   │   └── lib/            # Typed API client, currency formatters
│   └── Dockerfile          # Frontend container image definition
├── docs/                   # Deep dives on architecture, system design, Razorpay setup
├── sample_data/            # Sample statement fixtures (HDFC, ICICI, SBI)
└── docker-compose.yml      # PostgreSQL 15, Redis 7, Backend & Frontend services
```

---

## Documentation Index

Explore the detailed architecture, system design, and developer guides:

| Document | Audience | What It Covers |
|---|---|---|
| [PROJECT-OVERVIEW.md](./PROJECT-OVERVIEW.md) | Everyone / CAs / Judges | Business problem, core product principles, financial rules, edge cases, and benchmarks. |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Engineers & Architects | Detailed component design, data flow diagrams, async services, and security boundaries. |
| [SYSTEM-DESIGN.md](./SYSTEM-DESIGN.md) | Backend / DevOps | Non-functional requirements, queue architecture, rate limits, and failure modes. |
| [CONTRIBUTING.md](./CONTRIBUTING.md) | Developers | Local development workflow, multi-OS setup, testing guidelines, and PR requirements. |
| [backend/README.md](./backend/README.md) | Backend Engineers | Deep dive into FastAPI endpoints, Alembic migrations, database models, and test suites. |
| [docs/REPO_MAP.md](./docs/REPO_MAP.md) | Full Stack Engineers | Comprehensive source file map covering frontend components and backend services. |
| [docs/RAZORPAY-INTEGRATION.md](./docs/RAZORPAY-INTEGRATION.md) | Integrators | Razorpay REST API settlement sync, webhook HMAC verification, and cursor pagination. |

---

## License

This project is licensed under the [MIT License](./LICENSE).

Copyright (c) 2026 Akshay Haldar.
