# ReconGrid AI — Workflow Rules & Contribution Guidelines

## 1. Git Branching Strategy
* `main`: production-ready, fully verified, deployable.
* `dev`: primary integration branch.
* `feature/<feature-name>`: branched off `dev` (e.g., `feature/csv-ingestion`, `feature/razorpay-fetcher`, `feature/fuzzy-match-engine`).
* `fix/<bug-name>`: dedicated bug fix branches (e.g., `fix/webhook-signature-verification`).

---

## 2. Commit Conventions (Conventional Commits)
* `feat:` new feature — e.g. `feat(reconciliation): implement tier-2 fuzzy matching`
* `fix:` bug/regression patch — e.g. `fix(razorpay): correct pagination cursor offset`
* `docs:` documentation-only — e.g. `docs(architecture): add sequence diagram for diagnostics`
* `refactor:` restructuring, no behavior change — e.g. `refactor(csv): extract streaming parser utility`
* `chore:` tooling/build/deps — e.g. `chore(deps): add tenacity and httpx`
* `test:` test additions/updates — e.g. `test(diagnostics): add fee-deduction unit tests`

---

## 3. Pull Request Rules
* All feature branches target `dev` (never `main` directly).
* PRs with failing tests, build errors, or unresolved conflicts are not merged.
* Diff must be checked for `.env`, `.env.local`, and any private key material before merge — not assumed clean because `.gitignore` exists.
* Every PR requires self-review against the Definition of Done below.

---

## 4. Definition of Done (Backend — Python/FastAPI)
- [ ] **Linting/Formatting**: `ruff check .` and `black --check .` pass with zero errors.
- [ ] **Type Safety**: `mypy --strict app/services app/models` passes without errors.
- [ ] **Tests**: `pytest --cov` passes; coverage on `reconciliation.py`/`diagnostics.py` stays ≥90%.
- [ ] **Financial correctness**: no new `float` usage on monetary fields (grep-checked in review).
- [ ] **Error handling**: every external API/DB call wrapped in typed try/except with structured logging.
- [ ] **Security**: webhook routes verified against the HMAC dependency; no secrets committed.
- [ ] **Migrations**: schema changes tracked via `alembic revision --autogenerate` and tested locally, including a working `alembic downgrade`.
- [ ] **Documentation**: `README.md`/architecture docs updated if reconciliation rules or schemas changed.

## 4b. Definition of Done (Frontend — Next.js/TypeScript, unchanged)
- [ ] `npm run lint` and `npm run format:check` pass with zero errors/warnings.
- [ ] `npx tsc --noEmit` passes.
- [ ] No API secrets referenced client-side.

---

## 5. Incident & Rollback Procedure
* **Bad migration on shared dev DB**: run `alembic downgrade -1` immediately, notify the team in the shared channel before anyone else migrates further, then fix and re-submit as a new migration (never edit an already-applied migration file).
* **Leaked/rotated secret**: rotate the key in the Razorpay dashboard (or LLM provider console for `LLM_API_KEY`) immediately, update `.env` locally and in the deploy target, force-restart affected services, and confirm the old key is rejected — do not consider it resolved until verified against a live test call.
* **Bad deploy on `main`**: revert via `git revert` (not force-push/rewrite of shared history), redeploy, then root-cause before reapplying.

---

## 6. Test-Data & Environment Hygiene
* All synthetic/test-mode Razorpay data (test webhooks, seeded fixtures) is tagged `is_test_mode: true` at the row level and never mixed into a demo dataset presented as production-realistic without that flag visible.
* Local/dev/demo databases are kept separate; no demo run reads from a database that also received arbitrary manual testing that day.

---

## 7. Hackathon-Specific Rule: Document Every Real Bug
Every non-trivial bug and its fix gets one line in `BUGLOG.md` the day it happens — not reconstructed from memory before submission. This directly feeds Question 12 ("What broke, and how you got out") and is worth more to the final writeup than polishing UI copy. Log format:
```
[date] [component] what broke -> root cause -> fix -> time lost
```
