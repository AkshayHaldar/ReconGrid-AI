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

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Copy the environment template and fill in your values:

```bash
cp .env.example .env   # create this file if it doesn't exist
```

Required environment variables include database credentials and any API keys referenced in `backend/app/core/config.py`.

### 4. Set up the frontend

```bash
cd ../frontend
npm ci
cp .env.local.example .env.local  # if provided
```

### 5. Start the development servers

**Backend** (from `backend/`):
```bash
uvicorn app.main:app --reload --port 8000
```

**Frontend** (from `frontend/`):
```bash
npm run dev
```

The frontend runs on `http://localhost:3000` and proxies API calls to the backend at `http://localhost:8000`.

---

## Running the Test Suite

### Backend

```bash
cd backend
pytest
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

### Adding a Bank Parser

Bank-specific CSV/PDF parsing logic lives in `backend/app/parsers/`. Each parser is a Python class that:

1. Inherits from `BaseBankParser`.
2. Implements `can_parse(filename: str) -> bool` — returns `True` for file names or headers this parser recognises.
3. Implements `parse(file_content: bytes) -> list[BankTransaction]` — returns a list of normalised `BankTransaction` objects.

Steps:

1. Create `backend/app/parsers/<bank_name>_parser.py`.
2. Implement the two required methods.
3. Register the parser in `backend/app/parsers/__init__.py` by adding it to `REGISTERED_PARSERS`.
4. Add fixtures to `sample_data/` for your bank's CSV/PDF format.
5. Write tests in `backend/tests/parsers/test_<bank_name>_parser.py`.

### Adding a Settlement Provider

Settlement provider integrations live in `backend/app/providers/`. Each provider fetches and normalises settlement data from an external API.

1. Create `backend/app/providers/<provider_name>_provider.py`.
2. Implement the `SettlementProvider` protocol: `fetch_settlements(from_date, to_date) -> list[Settlement]`.
3. Register the provider and update the provider factory.
4. Store API credentials as environment variables (never hardcode them).
5. Write tests using mocked HTTP responses.

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
