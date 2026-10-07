# ReconGrid AI

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-brightgreen.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-teal.svg)](https://fastapi.tiangolo.com)
[![Next.js 14](https://img.shields.io/badge/Next.js-14.2-black.svg)](https://nextjs.org)
[![Razorpay Buildathon Track 04](https://img.shields.io/badge/Razorpay_Buildathon-Track_04:_AI_Finance_Controller-blue)](https://razorpay.com)
[![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-green.svg)](./contribution.md)

An open-source settlement reconciliation and discrepancy diagnostic engine with an audited Q&A agent for Razorpay merchants and finance teams.

Originally built for the **Razorpay Buildathon 2026 (Track 04: AI Finance Controller)**, ReconGrid AI automates the painful process of matching bank statements against Razorpay payment gateway settlements.

---

## The Problem

If you run a business in India accepting payments via Razorpay, your finance team or Chartered Accountant spends hours at month-end cross-checking bank statements against settlement reports.

The numbers rarely match 1-to-1 because:
- **Gateway fees:** Razorpay deducts a 2% MDR fee plus 18% GST on each transaction.
- **Statutory taxes:** E-commerce sales have 1% Section 194-O TDS deducted at source.
- **Mid-cycle refunds:** Customer refunds get deducted from subsequent settlement batches.
- **Messy bank exports:** Indian banks (SBI, HDFC, ICICI, Axis) export statements with non-standard preambles, encrypted PDFs, and UTRs buried in long transaction descriptions.
- **Batched payouts:** Multiple orders are often paid out as a single lump sum in the bank statement.

Manual VLOOKUP in Excel is slow, error-prone, and painful. Naive LLM solutions fail because LLMs hallucinate numbers and cannot be trusted with financial math.

ReconGrid AI solves this by keeping a **hard separation**: all math, reconciliation, and ledger operations are 100% deterministic code using Python `Decimal` (zero floats), while AI is used strictly for read-only natural language explanations backed by anti-hallucination guardrails.

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
| **Zero-Float Conservation** | End-to-end Python `Decimal(18, 2)` arithmetic with schema-level rejection of IEEE 754 floats. Mathematical row conservation guaranteed: $\sum(\text{all tiers} + \text{exceptions} + \text{pending}) = \text{total ingested}$. | `pytest backend/tests/unit/test_schema_float_rejection.py` |

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

- **Backend:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), SQLite (dev/test) / PostgreSQL (prod)
- **Frontend:** Next.js 14 (App Router), TypeScript, Tailwind CSS, Lucide icons
- **Payment Gateway:** Razorpay REST API (settlements, payments, refunds, HMAC-SHA256 webhooks)
- **AI / LLM:** NVIDIA NIM (LLaMA 3.3 70B) for read-only explanations with strict regex guardrail

---

## Quickstart

### Prerequisites
- Python 3.11+
- Node.js 18+
- Git

### 1. Clone the Repository
```bash
git clone https://github.com/AkshayHaldar/ReconGrid-AI.git
cd ReconGrid-AI
```

### 2. Backend Setup
```bash
cd backend
python -m venv .venv

# On Windows:
.venv\Scripts\activate
# On macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

Start the API server:
```bash
uvicorn app.main:app --reload --port 8000
```
Interactive API documentation will be available at [http://localhost:8000/docs](http://localhost:8000/docs).

### 3. Frontend Setup
In a new terminal:
```bash
cd frontend
npm install
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) to view the reconciliation dashboard.

### 4. (Optional) Run with Docker Compose
If you prefer running PostgreSQL 15 and Redis locally:
```bash
docker compose up -d
```

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
```

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

If you want to contribute, please check [contribution.md](./contribution.md).

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
├── backend/
│   ├── app/
│   │   ├── api/v1/         # Route handlers (bank, razorpay, reconciliation, qa, webhooks)
│   │   ├── core/           # Config, database, security (HMAC), logging
│   │   ├── models/         # SQLAlchemy async models
│   │   ├── schemas/        # Pydantic v2 validation models
│   │   ├── services/       # Ingestion, matching engine, diagnostics, Q&A agent
│   │   └── utils/          # Decimal money helpers, CSV streaming, fuzzy string logic
│   ├── scripts/            # Benchmarks, synthetic data seeder, scorecard CLI
│   └── tests/              # Unit, integration, and messy fixture test suites
├── frontend/
│   ├── src/
│   │   ├── app/            # Next.js App Router (dashboard page and layout)
│   │   ├── components/     # Table, drawers, summary cards, Q&A slide-out
│   │   └── lib/            # Typed API client, currency formatters
├── docs/                   # Deep dives on architecture, system design, Razorpay setup
├── sample_data/            # Sample statement fixtures (HDFC, ICICI, SBI)
└── docker-compose.yml      # PostgreSQL 15 & Redis 7 services
```

---

## License

This project is licensed under the [MIT License](./LICENSE).

Copyright (c) 2026 Akshay Haldar.
