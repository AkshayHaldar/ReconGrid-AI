# 🔍 ReconGrid AI

**Autonomous settlement reconciliation and discrepancy-diagnostic engine with Settlement Q&A Agent for Razorpay merchants.**

Built for the Razorpay Buildathon — Track 04 (AI Finance Controller).

---

## 🧠 What Is This?

If you're an SME founder, a Chartered Accountant, or a finance ops person using Razorpay, you know the pain — every month, you sit down with a bank statement CSV in one tab and a Razorpay settlement report in another, and you spend hours (sometimes days) doing VLOOKUPs trying to figure out why the numbers don't match.

**ReconGrid AI automates that entire process.**

You upload your bank statement, it pulls your Razorpay settlements, and a deterministic matching engine tells you exactly:
- ✅ Which transactions matched perfectly
- 🔍 Which ones are close matches (needing a quick human review)
- ❌ Which ones couldn't be resolved (with a clear reason why)

And here's the twist — there's a **Settlement Q&A Agent** on top. You can literally type *"Why didn't order #4521 settle correctly?"* and get a plain-English answer. But unlike ChatGPT-style guessing, this answer is **sourced from an already-computed audit record** — the AI explains facts, it never invents them.

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
- Razorpay test-mode account ([setup guide →](./RAZORPAY-INTEGRATION.md))

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

Open [http://localhost:3000](http://localhost:3000) — you should see the reconciliation dashboard.

### 6. Try the Q&A Agent

```bash
curl -X POST http://localhost:8000/api/v1/qa/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "Why didn'\''t order #4521 settle correctly?"}'
```

---

## 🔄 How It Works (The Full Flow)

Here's what happens end-to-end when you use ReconGrid:

### Step 1: Upload Your Bank Statement
You upload a CSV from your bank (HDFC, ICICI, SBI, Axis, Kotak, etc.). The system:
- Validates the file (type, size)
- Streams it row-by-row (never loads the whole file into memory)
- Normalizes each row into a standard format: date, amount, UTR, direction (credit/debit)
- Deduplicates using a SHA-256 hash — re-uploading the same file is safe, it won't create duplicates

### Step 2: Pull Razorpay Settlements
The system calls Razorpay's API to fetch your settlement and refund data:
- Cursor-paginated (handles any volume)
- Retries with exponential backoff on failures (max 5 attempts, then stops — never hangs)
- Also listens for real-time `settlement.processed` webhooks (HMAC-verified)

### Step 3: The Matching Engine Runs
This is a 4-tier deterministic pipeline — no AI, no guessing, just rules:

| Tier | Strategy | Result |
|---|---|---|
| **Tier 0** | Date window (±2 days) + exact amount — used when UTR is missing | `SUGGESTED` (weaker evidence → needs human approval) |
| **Tier 1** | UTR + exact amount match | `MATCHED` ✅ |
| **Tier 2** | Fuzzy string matching on descriptors (≥90% confidence) | `SUGGESTED` (human reviews) |
| **Tier 3** | Delta analysis: is the difference explained by fees + GST, refund batching, or FX? | Explained → diagnostic logged • Unexplained → `EXCEPTION` ❌ |

**Important rules:**
- All money math uses Python `Decimal` — never `float`. This is a financial tool, not a calculator app.
- If one settlement matches two bank rows → both become `CONFLICT` (confidence score 0.50). Resolving a conflict to allocate a settlement to Bank Row A automatically transitions competing rows to `EXCEPTION` (`AUTO_DISPLACED`), preventing double-credit.
- Every decision is logged in an immutable, append-only audit trail.

### Step 4: Review & Approve
On the dashboard, you see the full ledger:
- **Matched** records are done — no action needed
- **Suggested** records have a one-click Approve/Deny
- **Conflicts** open an interactive drawer displaying competing bank rows, with one-click **"Assign & Resolve"** (auto-displacing competing rows) or **"Dismiss / Mark Exception"** (clean unlinking)
- **Exceptions** show the raw data + reason code for manual investigation

### Step 5: Ask Questions (Q&A Agent)
The Settlement Q&A panel lets you ask things like:
- *"Why is order #4521 short by ₹900?"*
- *"What happened with settlement setl_Kjs9283jkd921?"*

The system:
1. Looks up the matching reconciliation record (deterministic DB query — no LLM)
2. Sends the record's data to the LLM with a strict prompt: *"Explain this in plain language — do NOT recalculate or invent numbers"*
3. Runs a guardrail: if the LLM response contains any number not present in the source record → response is rejected, a safe template fallback is shown instead
4. Logs the entire interaction for audit

---

## 🗂️ Project Structure

```
ReconGrid-AI/
├── README.md                  ← you are here
├── docker-compose.yml         ← Postgres + Redis for local dev
├── .env.example               ← all config vars (copy to backend/.env)
│
├── backend/
│   ├── app/
│   │   ├── main.py            ← FastAPI entrypoint
│   │   ├── api/v1/            ← route handlers
│   │   │   ├── bank.py        ← CSV upload
│   │   │   ├── razorpay.py    ← manual settlement sync
│   │   │   ├── reconciliation.py ← status, records, approve/deny, export
│   │   │   ├── qa.py          ← Q&A agent endpoints
│   │   │   ├── webhooks.py    ← Razorpay webhook receiver
│   │   │   └── demo.py        ← demo/seed helpers
│   │   ├── services/          ← business logic
│   │   │   ├── ingestion.py       ← CSV parsing & normalization
│   │   │   ├── razorpay_client.py ← Razorpay API client (httpx + retries)
│   │   │   ├── reconciliation.py  ← the 4-tier matching engine
│   │   │   ├── diagnostics.py     ← delta analysis (fees, GST, refunds, FX)
│   │   │   ├── settlement_qa.py   ← Q&A: retrieval + LLM narration
│   │   │   └── guardrail.py       ← blocks LLM-invented numbers
│   │   ├── models/            ← SQLAlchemy ORM models
│   │   ├── schemas/           ← Pydantic request/response schemas
│   │   ├── repositories/      ← DB query layer (isolated from services)
│   │   ├── core/              ← config, security, logging, database
│   │   └── utils/             ← CSV parser, fuzzy matching, Decimal helpers
│   ├── tests/
│   │   ├── unit/              ← money, CSV, fuzzy, guardrail, diagnostics tests
│   │   ├── integration/       ← full pipeline, webhook, API route tests
│   │   └── fixtures/          ← synthetic test data (50+ records)
│   ├── scripts/
│   │   └── seed_test_transactions.py  ← generate Razorpay test data
│   ├── requirements.txt
│   └── pyproject.toml         ← ruff, black, mypy, pytest config
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   └── page.tsx       ← main dashboard page
│   │   └── components/
│   │       ├── Header.tsx
│   │       ├── SummaryCards.tsx      ← total ingested, match rate, exceptions
│   │       ├── FilterBar.tsx         ← filter by status
│   │       ├── ReconciliationTable.tsx ← the main ledger
│   │       ├── StatusBadge.tsx       ← color + icon badges
│   │       ├── SettlementQaPanel.tsx  ← Q&A side panel
│   │       ├── UploadModal.tsx       ← CSV upload flow
│   │       ├── DemoSyncModal.tsx     ← demo settlement sync
│   │       ├── ConflictDrawer.tsx    ← resolve conflicting matches
│   │       └── ExceptionDrawer.tsx   ← manual audit view
│   ├── package.json
│   ├── tailwind.config.js
│   └── tsconfig.json
│
└── docs/                      ← detailed documentation
    ├── ARCHITECTURE.md        ← component design, DB schema, security
    ├── SYSTEM-DESIGN.md       ← NFRs, sequence diagrams, failure matrix
    ├── RAZORPAY-INTEGRATION.md ← test-mode setup, endpoints, webhooks
    ├── CODE-STANDARDS.md      ← conventions, testing bar, financial rules
    ├── WORKFLOW-RULES.md      ← git process, definition of done
    ├── UX-CONTEXT.md          ← persona, wireframes, UI states
    └── BUGLOG.md              ← real bugs hit during the build
```

---

## 🔌 API Reference

All endpoints live under `/api/v1`.

| Method | Endpoint | What It Does |
|---|---|---|
| `POST` | `/bank/upload` | Upload a bank statement CSV |
| `POST` | `/razorpay/sync` | Manually trigger a settlement/refund pull from Razorpay |
| `POST` | `/webhooks/razorpay` | Receive Razorpay webhooks (HMAC-verified) |
| `GET` | `/reconciliation/{batch_id}/status` | Get batch summary — match rate %, ₹ reconciled, counts |
| `GET` | `/reconciliation/{batch_id}/records?status=` | Filtered list of records by status |
| `POST` | `/reconciliation/records/{record_id}/approve` | Approve a suggested match |
| `POST` | `/reconciliation/records/{record_id}/deny` | Deny a suggested match |
| `GET` | `/reconciliation/{batch_id}/export` | Export the full ledger (CSV/JSON) |
| `POST` | `/qa/ask` | Ask the Settlement Q&A Agent a question |
| `GET` | `/qa/history` | View past Q&A interactions (audit trail) |

**Error responses** follow a consistent format:
```json
{
  "success": false,
  "error": {
    "code": "RAZORPAY_API_RATE_LIMIT",
    "message": "Razorpay rate limit reached. Retrying with backoff.",
    "details": null
  }
}
```

---

## 🗄️ Database Schema

Five core tables power the reconciliation:

| Table | Purpose |
|---|---|
| `bank_transactions` | Normalized rows from uploaded bank CSVs (deduplicated by row hash) |
| `razorpay_settlements` | Settlement data from Razorpay API + webhooks (deduped by settlement_id) |
| `reconciliation_logs` | Every match/suggestion/exception decision — immutable, append-only |
| `qa_interaction_logs` | Every Q&A question + answer + guardrail result — fully auditable |
| `webhook_events` | Processed webhook event IDs (prevents duplicate processing) |

**Key design choices:**
- All monetary columns are `Decimal(18,2)` — never floating point
- `reconciliation_logs` rows are never updated or deleted — corrections are new rows that reference the superseded one
- `bank_transactions` uses a SHA-256 row hash as an idempotency key

---

## 🧪 Running Tests

```bash
cd backend

# Run all 69 unit and integration tests
pytest -v

# Run with full coverage report (96% backend coverage)
pytest --cov=app --cov-report=term-missing

# Run the golden test batch (50+ record synthetic dataset)
pytest tests/integration/test_synthetic_batch.py -v
```

The synthetic batch test runs the full pipeline and prints:
- Match rate %
- Total ₹ reconciled
- The unedited exception list

This is the exact output that goes into the hackathon submission.

---

## 🔐 Security Model

| Concern | How It's Handled |
|---|---|
| **API secrets** | Backend-only `.env` — never referenced in frontend code |
| **Webhook verification** | HMAC-SHA256 over raw request body, constant-time comparison, runs *before* JSON parsing |
| **Duplicate webhooks** | Deduped by `event_id` with a DB unique constraint |
| **CSV injection** | MIME/size validation, no formula execution, streamed parsing with bounded memory |
| **Money precision** | `Decimal`-only end-to-end — `float` is a blocking review comment |
| **LLM safety** | LLM output is guardrailed against the source record — invented numbers are rejected |

---

## 🎯 What Makes This Different

Most reconciliation tools either:
1. **Do simple matching** — UTR match, done. But what about fee deductions? Refund clawbacks? Split settlements?
2. **Let an AI guess** — throw everything at GPT and hope it gets the math right.

ReconGrid does neither. The matching engine is **100% deterministic** — same inputs always produce the same output. The AI is confined to one job: **explaining already-computed results in plain English**. If the AI tries to make up a number, a guardrail catches it and falls back to a template. Every answer links back to the exact source record.

This is a **verification and audit tool** — not a prediction engine.

---

## 📊 Key Metrics (Hackathon Submission)

| Metric | Value |
|---|---|
| Match rate on synthetic batch | Run `pytest tests/integration/test_synthetic_batch.py` to see |
| Total ₹ reconciled | Printed by the test above |
| Exception list | Unedited, with reason codes |
| Audit trail | End-to-end: raw CSV row → matched settlement → diagnostic → log entry |
| Automated Test Coverage | **69 tests passing (100%), 96% backend code coverage** |

---

## 📚 Documentation

For deeper dives into specific areas:

| Document | What You'll Learn |
|---|---|
| [Architecture](./ARCHITECTURE.md) | Component design, DB schema (with Mermaid diagrams), security boundaries, API reference |
| [System Design](./SYSTEM-DESIGN.md) | NFRs, capacity estimates, sequence diagrams for every flow, failure/recovery matrix, threat model |
| [Razorpay Integration](./RAZORPAY-INTEGRATION.md) | Test-mode setup, API endpoints used, webhook verification code, error handling matrix |
| [Code Standards](./CODE-STANDARDS.md) | Folder structure, linting/formatting rules, testing bar, financial correctness rules |
| [Workflow Rules](./WORKFLOW-RULES.md) | Git branching, commit conventions, PR process, definition of done, incident procedures |
| [UX Context](./UX-CONTEXT.md) | User persona (Ramesh), wireframes, all UI states including error/empty/loading/conflict |
| [Bug Log](./BUGLOG.md) | Real bugs hit during the build — root causes, fixes, time lost |

---

## 🏁 Current Status

**Prototype under active development** for the Razorpay Buildathon (submission: Sep 5, 2026).

What's working:
- ✅ Bank CSV ingestion with auto-detection and deduplication
- ✅ Razorpay settlement sync (API + webhooks)
- ✅ 4-tier matching engine with full diagnostics & batched subset sums
- ✅ Deterministic multi-candidate conflict locking & automatic competing row displacement
- ✅ Settlement Q&A Agent with LLM guardrails
- ✅ Next.js dashboard with high-density ledger & conflict resolution drawer
- ✅ Comprehensive test suite (69 tests, 96% backend coverage)

---

## 📝 License

This project was built for the Razorpay Buildathon hackathon.

---

*Built by [Akshay](https://github.com/Akshayhaldar) — because no CA should waste their month-end doing VLOOKUPs in 2026.*
