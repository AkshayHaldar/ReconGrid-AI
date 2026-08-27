# ReconGrid AI

Autonomous settlement reconciliation and discrepancy-diagnostic engine  with Settlement Q&A Agent for Razorpay merchants. Built for Razorpay buildathon — Track 04 (AI Finance Controller).

## What it does
Matches bank statement CSVs against Razorpay settlement/refund data using a deterministic, tiered matching engine, and produces a verifiable match rate %, total ₹ reconciled, and an honest exception list — with a full, immutable audit trail. On top of that, a **Settlement Q&A Agent** lets a finance user ask plain-language questions ("why didn't order #4521 settle correctly?") and get an answer narrated from an already-computed, independently-verifiable record — never a free-form LLM guess. See `PROJECT-OVERVIEW.md` for the full pitch and `SYSTEM-DESIGN.md` for why it's built this way.

## Docs Index
| Doc | What's in it |
|---|---|
| [`PROJECT-OVERVIEW.md`](./PROJECT-OVERVIEW.md) | Problem, solution, scope, success metrics, stopping conditions |
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | Component design, DB schema, security boundaries |
| [`SYSTEM-DESIGN.md`](./SYSTEM-DESIGN.md) | NFRs, capacity, sequence diagrams, failure/recovery matrix |
| [`RAZORPAY-INTEGRATION.md`](./RAZORPAY-INTEGRATION.md) | Test-mode setup, endpoints used, webhook verification |
| [`CODE-STANDARDS.md`](./CODE-STANDARDS.md) | Python/FastAPI conventions, testing bar, financial correctness rules |
| [`WORKFLOW-RULES.md`](./WORKFLOW-RULES.md) | Git/PR process, DoD, incident/rollback procedure |
| [`UX-CONTEXT.md`](./UX-CONTEXT.md) | Persona, wireframes, all UI states including edge cases |

## Quickstart (once scaffolded)
```bash
# Backend
cd backend
cp .env.example .env   # fill in Razorpay test keys
docker compose up -d postgres redis
poetry install
alembic upgrade head
uvicorn app.main:app --reload

# Seed synthetic test data (see RAZORPAY-INTEGRATION.md §3)
python scripts/seed_test_transactions.py --count 60

# Ask the Q&A agent something (once wired up)
curl -X POST localhost:8000/api/v1/qa/ask -d '{"query":"why didn'\''t order #4521 settle correctly?"}'

# Frontend
cd frontend
npm install
npm run dev
```

## Building this repo with an agentic coding tool
Every doc in this repo is written to be self-contained enough to hand directly to an agentic IDE (e.g. Antigravity) as a build spec  `ARCHITECTURE.md` has exact file paths, the API table, and the DB schema; `CODE-STANDARDS.md` has the folder structure and non-negotiable rules (Decimal-only money, LLM narrates-never-computes); `SYSTEM-DESIGN.md` has sequence diagrams for every major flow. Feed the agent `ARCHITECTURE.md` + `CODE-STANDARDS.md` first — they define *what* to build and *how it must be structured* — then `SYSTEM-DESIGN.md` for the exact request/response flow of each endpoint.

## Test Batch & Match Rate
Run `pytest tests/integration/test_synthetic_batch.py` — this runs the full pipeline against the committed 50+ record synthetic dataset in `tests/fixtures/synthetic_batch.json` and prints the match rate %, total ₹ reconciled, and the unedited exception list, exactly as it will be shown in the submission write-up.
