# 🔍 ReconGrid AI

**Autonomous settlement reconciliation and discrepancy-diagnostic engine with Settlement Q&A Agent for Razorpay merchants.**

Built for the Razorpay Buildathon — Track 04 (AI Finance Controller).

---

## 🧠 What Is This?

If you're an SME founder, a Chartered Accountant, or a finance ops manager using Razorpay, you know the pain: every month, you sit down with a bank statement in one tab and a Razorpay settlement report in another, and spend hours (sometimes days) doing VLOOKUPs trying to figure out why the numbers don't match.

**ReconGrid AI automates that entire process.**

You upload your bank statement (CSV or PDF, even password-protected), it ingests your Razorpay settlements, and a deterministic matching engine tells you exactly:
- ✅ Which transactions matched perfectly (Tier 1 & Tier 1.5)
- 🔍 Which ones are fuzzy or fallback candidates needing single-click CA approval (Tier 2 & Tier 0)
- ⚖️ Which payouts have multiple competing bank claims (`CONFLICT` locking to prevent double-credit)
- ⏳ Which transactions are awaiting settlement within the T+2 window (`PENDING_SETTLEMENT_DATA`)
- ❌ Which ones are true discrepancies or fee/tax/refund adjustments with root-cause diagnostics (Tier 3)

And here's the twist — there's a **Settlement Q&A Agent** on top. You can type *"Why didn't order #4521 settle correctly?"* and get a plain-English explanation. Unlike ChatGPT-style guessing, this answer is **sourced from an already-computed audit record** — the AI explains facts and is strictly guardrailed against inventing numbers.

---

## 🏛️ System Architecture

```
                                    RECONGRID-AI SYSTEM ARCHITECTURE
                                    
  [ Bank Statements ]              [ Razorpay Gateway ]
    (CSV / Multi-page PDF)           (API / HMAC Webhooks)
             │                                │
             ▼                                ▼
┌─────────────────────────┐      ┌─────────────────────────┐
│ Ingestion & Resilient   │      │ Cursor-Paginated Sync   │
│ Normalization Engine    │      │ & Webhook Ingestion     │
│ • Preamble skip (SBI)   │      │ • Net = Gross - Fee-Tax │
│ • BOM & ₹ parsing       │      │ • Section 194-O TDS     │
│ • Embedded UTR extract  │      │ • Refund clawbacks      │
│ • Zero-float Decimal    │      │ • Deduplicated (Id)     │
└────────────┬────────────┘      └────────────┬────────────┘
             │                                │
             └────────────────┬───────────────┘
                              ▼
        ┌───────────────────────────────────────────┐
        │  Deterministic Multi-Tier Matching Engine  │
        │                                           │
        │  Tier 1:   Exact UTR + Net Amount Match   │
        │  Tier 1.5: Prefix/Substring UTR Match     │
        │  Tier 2:   Descriptor Fuzzy Match (>=90%) │
        │  Tier 0:   Date Window (+/-2d) + Amount   │
        │  Tier 3:   Batched Subset-Sum & Delta     │
        │  Conflict: Multi-candidate Lock & Displace│
        └─────────────────────┬─────────────────────┘
                              │
             ┌────────────────┴────────────────┐
             ▼                                 ▼
┌─────────────────────────┐      ┌─────────────────────────┐
│ Audit Ledger & Cards    │      │ Settlement Q&A Agent    │
│ • Append-Only Audit DB  │      │ • Deterministic Query   │
│ • Scorecard & Metrics   │      │ • LLM Narration         │
│ • CSV Audit Export      │      │ • Anti-Hallucination    │
│ • One-Click Approvals   │      │   Regex Guardrail       │
└─────────────────────────┘      └─────────────────────────┘
```

---

## 🛡️ How ReconGrid-AI Handles Messy Real-World Data

Real financial statements from Indian banks are notorious for breaking standard parsers. ReconGrid-AI is engineered with 30+ years of mission-critical financial software practices:

1. **Bank Preamble Resilience:**
   1990s/2000s core banking software (e.g. SBI, HDFC) outputs 5–8 lines of account metadata before the actual table header. ReconGrid dynamically scores candidate header rows across multi-bank dialects to skip preambles automatically.
2. **Indian Currency & Notation Normalization:**
   Correctly handles UTF-8 BOM (`﻿`), currency symbols (`₹`, `INR`, `Rs.`), lakh/crore commas (`1,23,456.78`), column suffixes (`Cr` / `Dr`), and accounting parentheses `(5,000.00)`.
3. **Embedded UTR Tokenization:**
   Extracts valid 8–24 character banking UTR/RRN tokens embedded inside free-form NEFT/RTGS/UPI narrations (e.g. `NEFT CR-HDFC N296250485376 RAZORPAY SETTLEMENT`) while excluding reserved banking keywords (`RAZORPAY`, `SETTLEMENT`, `BANGALORE`).
4. **Zero-Float Financial Precision & Unscaled Paise Protection:**
   Uses Python `Decimal` with `ROUND_HALF_UP` end-to-end. Rejects unscaled integer paise imports (e.g. `5000000` instead of `50000.00`) with actionable error messages.
5. **Password-Protected Multi-Page PDFs:**
   Ingests encrypted statements from HDFC, ICICI, SBI, Axis, Kotak with automated bank password formula cheat sheets and decryption fallbacks.
6. **Graceful Row-Level Error Isolation:**
   A corrupted row in a 5,000-line statement never crashes the upload with a raw 500. Corrupted rows are isolated and surfaced in `validation_errors`, while all valid rows are ingested and reconciled immediately.

---

## 🏆 Razorpay Buildathon Track 04 (AI Finance Controller) Compliance & Scorecard

ReconGrid-AI is architected directly against the official Track 04 mandate: *"Build finance-ops agents that close the loop over synthetic data with 50+ record batches, reporting match rates and unresolved anomalies... Verification capacity, not generation speed, is the bottleneck."*

### 📊 THE BAR — Compliance Matrix

| Track Requirement | Where Satisfied in ReconGrid-AI | Verification Command / Metric |
|---|---|---|
| **High-Throughput Batch Processing** | Deterministic multi-tier engine with precomputed UTR indices & bulk persistence | `python backend/scripts/benchmark_throughput.py`<br>• **50 records:** 0.047s (1,043 rows/s)<br>• **1,000 records:** 2.76s (361 rows/s)<br>• **5,000 records:** 26.98s (185 rows/s) |
| **Measured Accuracy & Tiered Match Rates** | Strict deterministic multi-tier pipeline: Tier 1 (Exact UTR), Tier 1.5 (Normalized UTR), Tier 2 (Fuzzy Descriptor), Tier 0 (Date Window Fallback), Tier 3 (Fee/GST/TDS Diagnostics & Subset Sum) | `GET /api/v1/reconciliation/{batch_id}/scorecard`<br>• **Tier 1:** Net & Gross exact reference matches<br>• **Tier 2:** $\ge 90\%$ fuzzy token similarity<br>• **Tier 0:** $\pm 3$ day date window + amount fallback |
| **Honest Lists of Unresolved Anomalies** | Zero-silent-drop policy. Precision over recall. Seeded true exceptions remain unresolved with explicit diagnostic codes (`UNRESOLVED`, `FEE_DEDUCTION`, `REFUND_ADJUSTED`, `TDS_194O_DEDUCTION`, `PENDING_SETTLEMENT`). | `python backend/scripts/generate_scorecard_report.py`<br>• Full unfiltered exception ledger output<br>• Precise root-cause notes for every anomaly |
| **Closed-Loop Finance Controller** | End-to-end operational cycle: Statement Ingest $\rightarrow$ Gateway Sync $\rightarrow$ Deterministic Match $\rightarrow$ Anomaly Flagging $\rightarrow$ Q&A Explanation $\rightarrow$ Human CA Resolution with Automated Competitor Displacement | `pytest backend/tests/integration/test_synthetic_batch.py`<br>`pytest backend/tests/integration/test_api_routes.py` |
| **Zero-Float Mathematical Conservation** | Python `Decimal` with `ROUND_HALF_UP` end-to-end. Pydantic v2 schema-level rejection of IEEE 754 floats. Strict row conservation: $\sum(\text{Matched} + \text{Suggested} + \text{Conflicts} + \text{Exceptions} + \text{Pending}) = \text{Total Ingested}$. | `pytest backend/tests/unit/test_schema_float_rejection.py`<br>`pytest backend/tests/unit/test_scorecard.py` |

---

### ⏱️ Batch Processing Throughput Benchmark

Tested on standard hardware using the full deterministic reconciliation pipeline, database persistence, and audit logging (`python backend/scripts/benchmark_throughput.py`):

```text
==========================================================================================
Batch Size   | Wall Time    | Throughput       | Peak Memory  | Match Rate   | Exceptions (INR)  | Conservation
------------------------------------------------------------------------------------------
50           | 0.0351s      | 1,424.5 rows/s   |     1.52 MB  |    96.00%    | 2 (INR 99,998)    | PASSED (0 lost)
200          | 0.1078s      | 1,855.3 rows/s   |     2.68 MB  |    95.00%    | 10 (INR 499,990)  | PASSED (0 lost)
500          | 0.3136s      | 1,594.4 rows/s   |     6.49 MB  |    94.80%    | 9 (INR 449,991)   | PASSED (0 lost)
1000         | 0.9716s      | 1,029.2 rows/s   |    12.88 MB  |    94.80%    | 17 (INR 849,983)  | PASSED (0 lost)
5000         | 32.6310s     |   153.2 rows/s   |    67.50 MB  |    94.72%    | 13 (INR 649,987)  | PASSED (0 lost)
==========================================================================================
```

---

### 📋 Audit Scorecard Generation CLI

To generate the audit scorecard report across any batch:
```bash
cd backend
python scripts/generate_scorecard_report.py --batch-id default
```

---

## 🎯 Demo Verification (cURL Guide)

You can verify the entire end-to-end reconciliation lifecycle directly from the terminal:

### 1. Seed 60-Record Synthetic Dataset (All Tiers & Edge Cases)
```bash
curl -X POST "http://localhost:8000/api/v1/demo/seed?count=60&batch_id=default" \
  -H "Content-Type: application/json"
```

### 2. Check Reconciliation Status Cards (Ramesh Dashboard Metrics)
```bash
curl -X GET "http://localhost:8000/api/v1/reconciliation/default/status"
```

### 3. Retrieve Audit-Grade Scorecard & Tier Breakdown
```bash
curl -X GET "http://localhost:8000/api/v1/reconciliation/default/scorecard"
```

### 4. Ask the Settlement Q&A Agent (Audited & Guardrailed)
```bash
curl -X POST "http://localhost:8000/api/v1/qa/ask" \
  -H "Content-Type: application/json" \
  -d '{"query": "Why did order 4521 settle with a delta?", "history": []}'
```

### 5. Fetch Ledger Records & Inspect Suggested / Conflict Rows
```bash
curl -X GET "http://localhost:8000/api/v1/reconciliation/default/records?status=SUGGESTED"
```

### 6. Single-Click Approve a Suggested Match
```bash
# Replace <RECORD_ID> with an actual record ID from the ledger
curl -X POST "http://localhost:8000/api/v1/reconciliation/records/<RECORD_ID>/approve" \
  -H "Content-Type: application/json" \
  -d '{"note": "Approved by CA after verifying client invoice."}'
```

### 7. Resolve a Conflict with Automatic Competitor Displacement
```bash
# Assigns settlement to chosen row and moves competing row to EXCEPTION
curl -X POST "http://localhost:8000/api/v1/reconciliation/records/<RECORD_ID>/resolve-conflict" \
  -H "Content-Type: application/json" \
  -d '{"chosen_settlement_id": "setl_Kjs9283jkd911", "note": "Allocated to Branch A after physical slip verification."}'
```

### 8. Download Complete Audit Ledger CSV
```bash
curl -X GET "http://localhost:8000/api/v1/reconciliation/default/export" \
  -o recongrid_audit_ledger.csv
```

---

## 🏗️ Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy (async) |
| **Database** | PostgreSQL (via Docker Compose) • SQLite for local dev/tests |
| **Queue / Cache** | Redis |
| **Frontend** | Next.js 14, React 18, Tailwind CSS, TypeScript |
| **External APIs** | Razorpay REST API (settlements, refunds, webhooks) |
| **AI / LLM** | NVIDIA NIM / LLaMA 3.3 70B (narration only — never for math) |

---

## ⚡ Quickstart

### Prerequisites
- Python 3.11+
- Node.js 18+
- Docker & Docker Compose (for Postgres + Redis)
- Razorpay test-mode account ([setup guide →](./docs/RAZORPAY-INTEGRATION.md))

### 1. Clone & Set Up Environment

```bash
git clone https://github.com/your-username/ReconGrid-AI.git
cd ReconGrid-AI
```

### 2. Start Infrastructure (Postgres + Redis)

```bash
docker compose up -d
```

This spins up:
- **PostgreSQL 15** on port `5432` (user: `recongrid`, db: `recongrid`)
- **Redis 7** on port `6379`

### 3. Backend Setup

```bash
cd backend
cp .env.example .env     # ← fill in your Razorpay test keys + LLM API key
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

> **Note:** The `.env.example` file has every config var documented. At minimum you need `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, and `RAZORPAY_WEBHOOK_SECRET`.

### 4. Seed Test Data

```bash
python scripts/seed_test_transactions.py --count 60
```

This creates synthetic transactions in your Razorpay test account so you have settlement data to reconcile against.

### 5. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) — you will see the high-density reconciliation dashboard.

---

## 🧪 Running Tests

```bash
cd backend

# Run all unit, integration, and e2e tests
pytest -v

# Run with full coverage report
pytest --cov=app --cov-report=term-missing

# Run the golden test batch (50+ record synthetic dataset)
pytest tests/integration/test_synthetic_batch.py -v

# Run dirty real-world messy fixtures e2e tests
pytest tests/integration/test_messy_fixtures_e2e.py -v
```

---


## 🔌 API Reference

All endpoints live under `/api/v1`.

| Method | Endpoint | What It Does |
|---|---|---|
| `POST` | `/bank/upload` | Upload a bank statement (CSV or PDF, optional password) |
| `GET` | `/bank/transactions` | List ingested bank statement transactions |
| `GET` | `/bank/password-hints` | Common Indian bank PDF password formula guide |
| `POST` | `/razorpay/sync` | Manually trigger a settlement/refund pull from Razorpay |
| `GET` | `/razorpay/settlements` | List stored Razorpay settlements |
| `POST` | `/webhooks/razorpay` | Receive Razorpay webhooks (HMAC-verified) |
| `GET` | `/reconciliation/{batch_id}/status` | Get summary cards metrics (match rate %, ₹ reconciled) |
| `GET` | `/reconciliation/{batch_id}/scorecard` | Audit-grade scorecard metrics with separate Tier 0/1/2/3 breakdown |
| `GET` | `/reconciliation/{batch_id}/records` | Filtered, paginated reconciliation records |
| `POST` | `/reconciliation/records/{id}/approve` | One-click approve a suggested match |
| `POST` | `/reconciliation/records/{id}/deny` | Move suggested match to exception |
| `POST` | `/reconciliation/records/{id}/resolve-conflict` | Assign settlement to specific bank row & auto-displace competitors |
| `GET` | `/reconciliation/{batch_id}/export` | Export the full ledger as CSV |
| `POST` | `/qa/ask` | Ask the Settlement Q&A Agent a question |
| `GET` | `/qa/history` | View past Q&A interactions (audit trail) |
| `POST` | `/demo/seed` | Seed 50+ record synthetic batch across all tiers |
| `POST` | `/demo/reset` | Clear test batch records |
| `GET` | `/demo/sample-statement` | Download sample CSV for HDFC, ICICI, or SBI |

---

## 📚 Documentation

For deeper dives into specific areas:

| Document | What You'll Learn |
|---|---|
| [Architecture](./docs/ARCHITECTURE.md) | Component design, DB schema, security boundaries, API reference |
| [System Design](./docs/SYSTEM-DESIGN.md) | NFRs, sequence diagrams for every flow, failure/recovery matrix |
| [Razorpay Integration](./docs/RAZORPAY-INTEGRATION.md) | Test-mode setup, API endpoints used, webhook verification code |
| [Code Standards](./docs/CODE-STANDARDS.md) | Financial correctness rules, Zero-Float policy, testing bar |
| [Workflow Rules](./docs/WORKFLOW-RULES.md) | Git branching, commit conventions, definition of done |
| [UX Context](./docs/UX-CONTEXT.md) | User persona (Ramesh), wireframes, all UI states |
| [Bug Log](./docs/BUGLOG.md) | Real bugs hit during the build — root causes, fixes, time lost |

---

## 📝 License

This project was built for the Razorpay Buildathon hackathon.

---

*Built by [Akshay](https://github.com/Akshayhaldar) — because no CA should waste their month-end doing VLOOKUPs in 2026.*
