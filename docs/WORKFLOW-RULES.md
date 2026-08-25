# ReconGrid AI — Workflow Rules & Contribution Guidelines

## 1. Git Branching Strategy

To maintain velocity while ensuring code stability during the hackathon and production cycles:

* `main`: Production-ready, fully verified, deployable codebase.
* `dev`: Primary integration branch where verified features converge.
* `feature/<feature-name>`: Isolated feature branches branched off `dev` (e.g., `feature/csv-ingestion-parser`, `feature/razorpay-fetcher`, `feature/fuzzy-match-engine`).
* `fix/<bug-name>`: Dedicated bug fix branches (e.g., `fix/webhook-signature-verification`).

---

## 2. Commit Conventions (Conventional Commits)

All commits must follow the **Conventional Commits** specification (`<type>(<scope>): <description>`):

* `feat:` Introduces a new feature.
  * *Example:* `feat(reconciliation): implement tier-2 fuzzy matching using levenshtein distance`
* `fix:` Patches a bug or regression.
  * *Example:* `fix(razorpay): correct pagination cursor offset in settlements fetcher`
* `docs:` Documentation-only modifications.
  * *Example:* `docs(architecture): add sequence diagram for discrepancy diagnostics`
* `refactor:` Code restructuring that neither adds a feature nor fixes a bug.
  * *Example:* `refactor(csv): streamline stream parser into dedicated utility class`
* `chore:` Build process, tooling, or package updates.
  * *Example:* `chore(deps): add string-similarity and razorpay sdk`
* `test:` Adding or updating unit/integration tests.
  * *Example:* `test(diagnostics): add unit test cases for fee deduction calculations`

---

## 3. Pull Request (PR) Rules

* **Branch Target**: All feature branches must target `dev` (never directly to `main`).
* **Zero Broken Code**: PRs with failing tests, build errors, or unresolved merge conflicts will not be merged.
* **Environment File Protection**: Verify that `.env`, `.env.local`, and private certificates are NOT tracked or committed in the PR diff.
* **Review & Verification**: Every PR requires self-review verification against the checklist below before merge.

---

## 4. Definition of Done (DoD)

Before any feature, endpoint, or engine enhancement is marked complete and merged:

- [ ] **Linting & Formatting**: Code passes `npm run lint` and `npm run format:check` with zero errors/warnings.
- [ ] **Type Safety**: Full TypeScript compilation (`npm run build` or `npx tsc --noEmit`) passes without errors.
- [ ] **Error Handling**: All external API calls (Razorpay, CSV streams, Database queries) are wrapped in try-catch with appropriate error logs and HTTP status codes.
- [ ] **Security & Validation**: Webhook endpoints enforce HMAC SHA256 signature verification; no API secrets or keys are hardcoded.
- [ ] **Database Migrations**: Any schema change is tracked in Prisma migrations (`npx prisma migrate dev`) and tested locally.
- [ ] **Documentation**: `README.md`, API route comments, or architecture docs are updated if reconciliation business rules or schemas change.
