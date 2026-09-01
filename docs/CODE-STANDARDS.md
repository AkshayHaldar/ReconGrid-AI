# 📋 Code Standards — ReconGrid AI

> **Backend:** Python 3.11+ / FastAPI  
> **Frontend:** Next.js 14 / TypeScript / Tailwind CSS

---

## 1. Backend Project Layout

```
recongrid-ai-backend/
├── .env.example
├── .gitignore
├── pyproject.toml              # ruff, black, mypy, pytest configs
├── app/
│   ├── main.py                 # FastAPI application entrypoint
│   ├── api/v1/                 # route handlers
│   │   ├── bank.py             # CSV upload
│   │   ├── razorpay.py         # manual settlement sync
│   │   ├── reconciliation.py   # status, records, approve/deny, export
│   │   ├── qa.py               # Q&A agent endpoints
│   │   ├── webhooks.py         # Razorpay webhook receiver
│   │   └── demo.py             # seed / demo helpers
│   ├── core/
│   │   ├── config.py           # Pydantic Settings (env vars)
│   │   ├── security.py         # HMAC verification, auth deps
│   │   ├── database.py         # SQLAlchemy engine & session maker
│   │   └── logging.py          # structlog configuration
│   ├── models/                 # SQLAlchemy ORM models
│   ├── schemas/                # Pydantic request & response models
│   ├── repositories/           # DB query layer (isolated from services)
│   ├── services/               # core business logic
│   │   ├── ingestion.py        # CSV parsing & normalization
│   │   ├── razorpay_client.py  # Razorpay API client
│   │   ├── reconciliation.py   # the 4-tier matching engine
│   │   ├── diagnostics.py      # delta analysis (fees, GST, refunds, FX)
│   │   ├── settlement_qa.py    # retrieval + LLM narration
│   │   └── guardrail.py        # numeric guardrail for LLM output
│   └── utils/
│       ├── fuzzy.py            # string similarity algorithms
│       ├── csv_parser.py       # streaming CSV parser
│       └── money.py            # Decimal helpers (no float coercion!)
└── tests/
    ├── unit/                   # money, CSV, fuzzy, diagnostics, guardrail tests
    ├── integration/            # full pipeline, webhook, API route tests
    └── fixtures/               # 50+ record synthetic test batch
```

---

## 2. Code Quality & Tooling

| Tool | Purpose | Standard |
|---|---|---|
| **Black** | Code formatting | Line length 100 |
| **Ruff** | Linting & import sorting | Zero warnings before merge |
| **Mypy** | Static type checking | Strict mode on `app/services` and `app/models` |
| **Pytest** | Testing | ≥90% coverage on reconciliation & diagnostics |

---

## 3. Financial Correctness Rules (Non-Negotiable ⚠️)

These are hard rules — not suggestions. A violation will block a PR.

### 1. No `float` for Money — Ever
All monetary fields must use Python's `Decimal` type from end to end:
- Pydantic schemas use `Decimal` (or `condecimal`)
- Database columns use `Numeric(18, 2)`
- All math is done with `Decimal` arithmetic
- Any `float` touching a money field in a PR diff is an immediate rejection

### 2. LLMs Narrate — They Never Calculate
The Settlement Q&A Agent is the **only** LLM-touching component. It is strictly a narration layer:
- The reconciliation engine computes everything first
- The LLM only explains the already-computed row in plain language
- `guardrail.py` extracts all numbers from the LLM's response and verifies them against the source row
- If the LLM invents a number → response is rejected, template fallback is shown, and the rejection is logged

### 3. Streamed Ingestion Only
Bank statement CSVs must be parsed row-by-row:
- Never `.read()` an entire file into memory
- File size and row count limits are enforced before parsing starts
- Bad files fail fast with structured errors

### 4. Wrapped External Calls
Every outbound API call (Razorpay, LLM providers) must be wrapped in explicit `try/except`:
- Use typed custom exceptions (`RazorpayFetchError`, `RazorpayFetchExhausted`)
- Use structured logging via `structlog`
- No bare `except:` or swallowed exceptions

---

## 4. Testing Bar

- **Reconciliation Engine:** ≥90% coverage on `reconciliation.py` and `diagnostics.py`
- **Rest of Codebase:** ≥70% coverage minimum
- **Golden Test Batch:** A committed 50+ record synthetic dataset (`tests/fixtures/synthetic_batch.json`) runs on every test pass. It asserts the match rate % against a known-good baseline.
- **Webhook Tests:** Must cover valid signature, invalid signature, missing header, duplicate `event_id`, and malformed JSON.
- **Q&A Guardrail Tests:** Must cover non-existent record lookups and adversarial cases where the LLM tries to invent numbers.

---

## 5. Naming Conventions

| Thing | Convention | Example |
|---|---|---|
| Functions & variables | `snake_case` | `fetch_settlement_batch()`, `is_amount_matching` |
| Pydantic schemas & ORM models | `PascalCase` | `BankTransaction`, `SettlementRecord` |
| Database tables & columns | `snake_case` | `bank_transactions`, `settlement_id` |
| Constants & env vars | `UPPER_SNAKE_CASE` | `RAZORPAY_KEY_ID`, `DEFAULT_PAGE_SIZE` |
| Python files | `snake_case.py` | `settlement_qa.py`, `csv_parser.py` |

---

## 6. Frontend Standards (Next.js / TypeScript)

- **Linter:** `next/core-web-vitals` + `@typescript-eslint/recommended`
- **Formatter:** Prettier (`singleQuote: true`, `tabWidth: 2`, `semi: true`, `printWidth: 100`)
- **Type Checking:** `npx tsc --noEmit` must pass with zero errors
- **Secrets:** Never reference secrets in client-side code — `.env.local` only, both gitignored

---

## 7. Error Handling

Every API error returns a standard envelope:

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

- Razorpay timeouts and `429`s retry with exponential backoff
- Hard failures halt the job loudly — no silent failures, no swallowed exceptions
