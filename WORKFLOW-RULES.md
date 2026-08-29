# 🔄 Workflow Rules & Guidelines — ReconGrid AI

---

## 1. Git Branching Strategy

```
main  ───────●──────────────────●────── (production-ready, verified)
             \                 /
dev   ────────●───────●───────●──────── (primary integration branch)
               \     / \     /
feature/*       ●───●   ●───●           (e.g., feature/csv-ingestion)
fix/*                    ●              (e.g., fix/webhook-signature)
```

- **`main`**: Production-ready, fully tested, deployable code
- **`dev`**: Daily integration branch where features merge first
- **`feature/<name>`**: Feature branches branched from `dev`
- **`fix/<name>`**: Bug fix branches

---

## 2. Commit Message Format (Conventional Commits)

Use standard prefixes so history stays readable:

| Type | When to Use | Example |
|---|---|---|
| `feat:` | A new feature | `feat(reconciliation): implement tier-2 fuzzy matching` |
| `fix:` | A bug fix | `fix(razorpay): correct pagination cursor offset` |
| `docs:` | Documentation changes only | `docs(readme): update setup instructions` |
| `refactor:` | Code change that doesn't fix a bug or add a feature | `refactor(csv): extract streaming parser utility` |
| `chore:` | Tooling, dependencies, config | `chore(deps): add tenacity and httpx` |
| `test:` | Adding or updating tests | `test(diagnostics): add fee-deduction test cases` |

---

## 3. Pull Request Checklist

Before merging any PR into `dev`:

- [ ] All tests pass (`pytest` in backend, `npm run build` in frontend)
- [ ] No `.env` or secret files are included in the diff
- [ ] Code is formatted and linted (`black`, `ruff`, `prettier`)
- [ ] No `float` used on money fields in Python code
- [ ] Any new edge cases have test coverage

---

## 4. Definition of Done

### Backend (Python / FastAPI)
- [ ] **Formatting:** `black --check .` passes
- [ ] **Linting:** `ruff check .` has zero warnings
- [ ] **Types:** `mypy --strict` passes on `app/services` and `app/models`
- [ ] **Tests:** `pytest --cov` passes; coverage on `reconciliation.py` and `diagnostics.py` ≥ 90%
- [ ] **Money Safety:** Zero `float` types in monetary math (use `Decimal` everywhere)
- [ ] **Security:** Webhook routes verify HMAC signatures; no secrets committed
- [ ] **Error Handling:** All external calls wrapped in typed try/except with structured logging

### Frontend (Next.js / TypeScript)
- [ ] `npm run lint` passes with zero errors
- [ ] `npx tsc --noEmit` passes with zero type errors
- [ ] No secrets or private API keys in client-side code

---

## 5. What to Do When Something Goes Wrong

### Leaked or Compromised Secret
1. Rotate the key in the Razorpay / LLM dashboard **immediately**
2. Update `.env` locally and on the server
3. Restart all services
4. Test with a live API call to confirm the old key is dead and the new one works

### Broken Deploy on `main`
1. Revert via `git revert` (never force-push or rewrite shared history)
2. Redeploy the previous working commit
3. Debug the issue in a `fix/` branch, test thoroughly, then re-merge

---

## 6. Real Bug Logging (Hackathon Rule 📝)

Every real bug hit during development gets logged in [`BUGLOG.md`](./BUGLOG.md) the day it happens.

This directly feeds the hackathon submission's *"What broke and how you fixed it"* section:

```markdown
## [YYYY-MM-DD] [component] Short title
- **Broke**: what actually happened
- **Root cause**: why it happened (not just the symptom)
- **Fix**: what was changed
- **Time lost**: rough estimate (e.g., ~30 mins)
```
