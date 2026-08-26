# ReconGrid AI — Code Standards & Engineering Guidelines

> **Stack note**: Backend standards below are for **Python 3.11+ / FastAPI**. Frontend (Next.js/TypeScript) standards are unchanged from the original spec and retained in Section 6.

## 1. Backend Folder Structure

```text
recongrid-ai-backend/
├── .env.example
├── .gitignore
├── pyproject.toml              # ruff, black, mypy, pytest config
├── alembic/                    # DB migrations
│   └── versions/
├── app/
│   ├── main.py                 # FastAPI app entrypoint
│   ├── api/
│   │   └── v1/
│   │       ├── bank.py         # /bank/upload
│   │       ├── razorpay.py     # /razorpay/sync
│   │       ├── reconciliation.py
│   │       ├── qa.py           # /qa/ask, /qa/history
│   │       └── webhooks.py     # /webhooks/razorpay
│   ├── core/
│   │   ├── config.py           # Pydantic Settings (env vars)
│   │   ├── security.py         # HMAC verification, auth deps
│   │   └── logging.py          # structlog config
│   ├── models/                 # SQLAlchemy/SQLModel ORM models
│   │   ├── bank_transaction.py
│   │   ├── razorpay_settlement.py
│   │   ├── reconciliation_log.py
│   │   ├── qa_interaction_log.py
│   │   └── webhook_event.py
│   ├── schemas/                # Pydantic request/response schemas
│   ├── services/
│   │   ├── ingestion.py
│   │   ├── razorpay_client.py
│   │   ├── reconciliation.py
│   │   ├── diagnostics.py
│   │   └── settlement_qa.py    # retrieval (deterministic) + LLM narration + guardrail
│   ├── repositories/           # DB query layer, isolated from services
│   └── utils/
│       ├── fuzzy.py            # string similarity
│       ├── csv_parser.py       # streaming CSV parser
│       └── money.py            # Decimal helpers, banned float coercion
└── tests/
    ├── unit/
    ├── integration/
    └── fixtures/                # synthetic bank + settlement test batches
```

---

## 2. Linting, Formatting & Type Safety
* **Formatter**: `black` (line length 100).
* **Linter**: `ruff` (replaces flake8 + isort), zero warnings before merge.
* **Type checking**: `mypy --strict` on `app/services` and `app/models` at minimum — the reconciliation engine is not allowed untyped code paths.
* **Pre-commit hooks**: `black`, `ruff`, `mypy` must all pass before a commit is accepted locally.

---

## 3. Testing Requirements
* **Framework**: `pytest` + `pytest-cov`.
* **Minimum coverage**: 90% on `app/services/reconciliation.py` and `app/services/diagnostics.py` specifically — these are the money-correctness modules and carry a higher bar than the rest of the codebase (70% overall minimum).
* **Golden test batch**: a fixed 50+ record synthetic dataset (`tests/fixtures/synthetic_batch.json`) covering exact matches, fuzzy matches, fee deductions, refund adjustments, missing UTRs, split settlements, and reversed settlements — run on every PR, with the resulting match rate % asserted against a known-good baseline so a regression is caught immediately, not at demo time.
* **Webhook tests** must include: valid signature, invalid signature, missing header, duplicate `event.id`, and malformed JSON body.
* **Q&A guardrail tests** must include: a query with no matching record (must return the deterministic "not found" response, never a guess), and at least one adversarial case where the LLM is mocked to return a fabricated number — the test asserts the guardrail rejects it and falls back to the template response.

---

## 4. Financial Correctness Rules (Non-Negotiable)
* **No `float` for money.** All monetary fields use Python `Decimal` end-to-end — Pydantic schemas, ORM columns (`Numeric(18,2)`), and all arithmetic. `float` in a diff touching money fields is a blocking review comment, not a style note.
* **No LLM-generated numbers.** The Settlement Q&A Agent (`app/services/settlement_qa.py`) is the only LLM-touching component in this codebase. It may only *narrate* a value that was already computed deterministically by the reconciliation engine — it may never compute or alter the number itself. Concretely: after the LLM generates a narration, `guardrail.py` extracts every numeric token from the response and checks it against the numeric fields on the source `ReconciliationLog` row; any number not present in the source row causes the response to be discarded in favor of a template-based fallback, and the rejection is logged to `QaInteractionLog.guardrail_rejected`.
* **Streaming ingestion only.** CSV files are processed row-by-row (`csv.reader` over a stream, or chunked `pandas.read_csv(chunksize=...)`) — never `.read()`'d fully into memory. A configured max file size and max row count are enforced before parsing begins.
* **All external API calls wrapped** in explicit `try/except` with typed exceptions (`RazorpayFetchError`, `RazorpayFetchExhausted`) and structured logging — no bare `except:`.

---

## 5. Naming Conventions (Backend)
* **Variables & functions**: `snake_case` (`fetch_settlement_batch`, `is_amount_matching`).
* **Pydantic schemas & SQLAlchemy models**: `PascalCase` (`BankTransaction`, `SettlementRecord`).
* **Database tables/columns**: `snake_case` (`bank_transactions`, `razorpay_settlements`).
* **Constants & env vars**: `UPPER_SNAKE_CASE` (`RAZORPAY_KEY_ID`, `DEFAULT_PAGE_SIZE`).
* **Files**: `snake_case.py`.

---

## 6. Frontend Standards (Next.js/TypeScript — unchanged)
* **ESLint**: `next/core-web-vitals`, `@typescript-eslint/recommended`.
* **Prettier**: `singleQuote: true`, `trailingComma: "all"`, `tabWidth: 2`, `semi: true`, `printWidth: 100`.
* **Pre-commit**: ESLint + Prettier must pass with 0 errors/warnings.
* **Zero hardcoded secrets** — all secrets in `.env.local`, `.env.example` kept blank, both gitignored.

---

## 7. Error Handling Paradigm (Backend)
* **Resilience first**: Razorpay timeouts, `429`s, or outages must never crash the API process or kill a background job silently.
* **Standardized JSON error structure**:
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
* **No swallowed exceptions**: every `except` block either re-raises a typed exception, logs with full context via `structlog`, or both — never a silent `pass`.
