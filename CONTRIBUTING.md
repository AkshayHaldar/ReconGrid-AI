# Contributing to ReconGrid AI

Thank you for your interest in contributing! This guide covers everything you need to get the project running locally and submit a quality pull request.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local Development Setup](#local-development-setup)
3. [Running the Test Suite](#running-the-test-suite)
4. [Linting and Type Checking](#linting-and-type-checking)
5. [Branch and Commit Conventions](#branch-and-commit-conventions)
6. [Pull Request Requirements](#pull-request-requirements)
7. [Extension Points](#extension-points)
   - [Adding a Bank Parser](#adding-a-bank-parser)
   - [Adding a Settlement Provider](#adding-a-settlement-provider)
8. [Working with Fixtures](#working-with-fixtures)
9. [Database Migrations](#database-migrations)

---

## Prerequisites

| Tool | Required version |
|------|-----------------|
| Python | 3.11+ |
| Node.js | 20+ |
| Docker & Docker Compose | any recent release |
| PostgreSQL | 15+ (or use Docker) |

---

## Local Development Setup

### 1. Clone the repository

```bash
git clone https://github.com/AkshayHaldar/ReconGrid-AI.git
cd ReconGrid-AI
```

### 2. Start backing services with Docker Compose

```bash
docker-compose up -d
```

This starts PostgreSQL and any other required services defined in `docker-compose.yml`.

### 3. Set up the backend

Navigate to `backend/` and create your virtual environment:

```bash
cd backend
python -m venv .venv
```

**Activate your virtual environment:**
* **Windows (PowerShell):**
  ```powershell
  .venv\Scripts\Activate.ps1
  ```
* **macOS / Linux:**
  ```bash
  source .venv/bin/activate
  ```

**Install dependencies in editable development mode:**
```bash
pip install -e ".[dev]"
```

Copy the environment template and initialize the database:

```bash
# Windows: copy .env.example .env
# macOS/Linux: cp .env.example .env
cp .env.example .env

# Run database migrations to initialize SQLite
alembic upgrade head
```

### 4. Set up the frontend

In a separate terminal:

```bash
cd frontend
npm install
```

### 5. Start the development servers

**Backend** (from `backend/` with `.venv` active):
```bash
uvicorn app.main:app --reload --port 8000
```
Interactive OpenAPI documentation will be live at [http://localhost:8000/docs](http://localhost:8000/docs).

**Frontend** (from `frontend/`):
```bash
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) to view the reconciliation dashboard.

---

## Running the Test Suite

### Backend

Run a fast sanity check (under 1 second):
```bash
cd backend
pytest tests/unit/test_matching_engine.py -v
```

Run all tests:
```bash
pytest -v
```

With coverage:

```bash
pytest --cov=app --cov-report=term-missing
```

### Frontend

```bash
cd frontend
npm run build   # verifies production build compiles without error
```

---

## Linting and Type Checking

### Backend

```bash
cd backend
ruff check .          # linting
black --check .       # formatting check
mypy .                # static type checking
```

To auto-fix linting and formatting issues:

```bash
ruff check . --fix
black .
```

### Frontend

```bash
cd frontend
npx tsc --noEmit      # TypeScript type check
npm run lint          # Next.js ESLint
npm run build         # production build check
```

---

## Branch and Commit Conventions

### Branch naming

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `feat/<short-description>` | `feat/add-icici-parser` |
| Bug fix | `fix/<short-description>` | `fix/razorpay-fee-rounding` |
| Documentation | `docs/<short-description>` | `docs/update-readme` |
| Refactoring | `refactor/<short-description>` | `refactor/matching-engine` |

### Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>

[optional body]

Closes #<issue-number>
```

Common types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.

---

## Pull Request Requirements

Before opening a PR:

- [ ] All existing tests pass (`pytest` for backend, `npm run build` for frontend).
- [ ] New code is covered by tests where applicable.
- [ ] Linting passes (`ruff check .` / `npm run lint`).
- [ ] Type checks pass (`mypy .` / `npx tsc --noEmit`).
- [ ] The PR description explains **what** changed and **why**.
- [ ] The PR references the related issue (e.g. `Closes #42`).

---

## Extension Points

### Adding Support for a New Bank (CSV / PDF)

Bank-specific statement parsing logic lives in `backend/app/utils/csv_parser.py` and `backend/app/utils/pdf_parser.py`, coordinated by `backend/app/services/ingestion.py`.

To add support for a new bank (e.g., Kotak, PNB, Bank of Baroda):

1. **Add bank dialect & column mappings:**
   - In `backend/app/utils/csv_parser.py`, add column headers and preamble-skipping rules for your bank.
   - Ensure transaction direction (`CREDIT` vs `DEBIT`), date format parsing, and UTR extraction regex handle the bank's narration format.
2. **Add sample statement fixtures:**
   - Place a small, anonymized statement in `sample_data/` (e.g., `sample_data/kotak_sample.csv`).
   - Ensure all amounts, names, and account numbers are synthetic.
3. **Write tests:**
   - Add unit tests in `backend/tests/unit/test_csv_parser.py` or integration tests in `backend/tests/integration/test_messy_fixtures_e2e.py` verifying clean extraction of `BankTransaction` records.

---

### Adding a New Payment Gateway Adapter

Payment gateway API interactions are encapsulated in `backend/app/services/razorpay_client.py`.

To add an adapter for another gateway (e.g., Cashfree, Stripe, PayU):

1. **Implement Gateway Client:**
   - Create a client class following the async `httpx` + `tenacity` retry pattern in `backend/app/services/`.
   - Ensure the client retrieves gross amounts, MDR fees, GST, TDS, refunds, and UTRs.
   - Convert all monetary units to Python `Decimal(18, 2)` rupees (converting gateway integer paise/cents if needed).
2. **Webhook Verification:**
   - Implement HMAC signature validation in `backend/app/api/v1/webhooks.py` (or a dedicated route) to reject unauthenticated payloads with HTTP 401.
3. **Write tests:**
   - Test mocked gateway pagination, retry backoff, and signature verification in `backend/tests/unit/`.

---

## Working with Fixtures

Test fixtures (sample bank statements and settlement reports) are stored in `sample_data/`. When adding new fixtures:

- Use **anonymised or synthetic data only** — never real customer data.
- Name files descriptively: `<bank>_<scenario>.<ext>` (e.g. `hdfc_partial_match.csv`).
- Keep file sizes small; a few rows are sufficient to cover the parsing scenario.
- Document the scenario the fixture represents in a comment at the top of the file or in a companion `README` in the same directory.

---

## Database Migrations

The project uses SQLAlchemy with Alembic for schema migrations.

To create a new migration after changing a model:

```bash
cd backend
alembic revision --autogenerate -m "describe the change"
```

To apply pending migrations:

```bash
alembic upgrade head
```

To roll back one step:

```bash
alembic downgrade -1
```

Always review the auto-generated migration file before committing to ensure it accurately reflects the intended schema change.
