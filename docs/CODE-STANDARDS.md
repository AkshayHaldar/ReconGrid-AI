# ReconGrid AI — Code Standards & Engineering Guidelines

## 1. Folder Structure (Decoupled Layered Architecture)

To ensure high maintainability, testability, and separation of concerns, the backend and frontend are organized cleanly:

```text
recongid-ai/
├── .env.example
├── .gitignore
├── .eslintrc.json
├── .prettierrc
├── package.json
├── prisma/
│   └── schema.prisma           # Prisma ORM schema & migrations
├── src/
│   ├── app/                    # Next.js App Router (UI Pages & Layouts)
│   │   ├── (dashboard)/
│   │   │   ├── reconciliation/
│   │   │   └── page.tsx
│   │   ├── api/                # API Route Handlers (Edge / Node runtime)
│   │   │   ├── bank/upload/
│   │   │   ├── razorpay/sync/
│   │   │   ├── reconcile/
│   │   │   └── webhooks/razorpay/
│   │   ├── layout.tsx
│   │   └── globals.css
│   ├── components/             # Reusable UI Components
│   │   ├── ui/                 # Atomic UI (Buttons, Badges, Modals, Tables)
│   │   ├── reconciliation/     # Domain components (ComparisonTable, DiagnosticPill)
│   │   └── common/             # Header, Sidebar, Nav
│   ├── controllers/            # Request orchestration & validation layer
│   │   ├── bank.controller.ts
│   │   ├── razorpay.controller.ts
│   │   └── reconcile.controller.ts
│   ├── services/               # Core business & domain logic
│   │   ├── ingestion.service.ts
│   │   ├── razorpay.service.ts
│   │   ├── reconciliation.service.ts
│   │   └── diagnostic.service.ts
│   ├── models/                 # Database queries & Prisma abstraction clients
│   │   └── db.ts
│   ├── types/                  # TypeScript interfaces and types
│   │   ├── bank.types.ts
│   │   ├── razorpay.types.ts
│   │   └── reconciliation.types.ts
│   └── utils/                  # Pure utility functions
│       ├── crypto.utils.ts     # Webhook HMAC verification
│       ├── csv.utils.ts        # Stream parsers & formatters
│       ├── fuzzy.utils.ts      # Levenshtein distance & string similarity
│       └── logger.utils.ts     # Structured logging
```

---

## 2. Linting & Formatting

* **ESLint**: Standardized ruleset (`next/core-web-vitals`, `@typescript-eslint/recommended`).
* **Prettier**: Strict formatting configuration:
  * `singleQuote`: `true`
  * `trailingComma`: `"all"`
  * `tabWidth`: `2`
  * `semi`: `true`
  * `printWidth`: `100`
* **Pre-commit Checks**: ESLint and Prettier must pass with 0 errors and 0 warnings before committing.

---

## 3. Security Rules

* **Zero Hardcoded Secrets**: Under no circumstances should API keys, webhook secrets, or database URLs be hardcoded into the repository.
* **Environment Variables**:
  * Store all secrets in `.env.local` or `.env`.
  * Maintain `.env.example` with blank placeholder values.
  * Ensure `.env` and `.env*.local` are explicitly defined in `.gitignore`.
* **Defensive Try-Catch Blocks**: Every controller, service method, and external API invocation must be wrapped in try-catch blocks with standardized HTTP error responses.
* **Webhook Signature Validation**: Every webhook payload MUST be validated using HMAC SHA256 before any business logic executes:
  ```typescript
  import crypto from 'crypto';

  export function verifyWebhookSignature(
    rawBody: string,
    signature: string,
    secret: string
  ): boolean {
    const expectedSignature = crypto
      .createHmac('sha256', secret)
      .update(rawBody)
      .digest('hex');
    return crypto.timingSafeEqual(
      Buffer.from(expectedSignature, 'utf-8'),
      Buffer.from(signature, 'utf-8')
    );
  }
  ```

---

## 4. Naming Conventions

* **Variables & Functions**: `camelCase` (e.g., `fetchSettlementBatch`, `isAmountMatching`, `bankTransactionId`).
* **React Components & Types/Interfaces**: `PascalCase` (e.g., `ComparisonTable`, `SettlementRecord`, `ReconciliationResponse`).
* **Database Tables & Columns (Prisma)**:
  * Database Table Mapping: `snake_case` (e.g., `bank_transactions`, `razorpay_settlements`).
  * Prisma Model Names: `PascalCase` (e.g., `BankTransaction`, `RazorpaySettlement`).
* **Constants & Environment Variables**: `UPPER_SNAKE_CASE` (e.g., `RAZORPAY_KEY_ID`, `DEFAULT_PAGE_SIZE`).
* **Filenames**:
  * Source code & utilities: `kebab-case.ts` or `name.service.ts` / `name.controller.ts`.
  * Components: `PascalCase.tsx` or `kebab-case.tsx`.

---

## 5. Error Handling Paradigm

* **Resilience First**: Razorpay API timeouts, rate limits (HTTP 429), or temporary outages must be handled gracefully without crashing the server or terminating background worker jobs.
* **Standardized JSON Error Structure**:
  ```json
  {
    "success": false,
    "error": {
      "code": "RAZORPAY_API_RATE_LIMIT",
      "message": "Razorpay rate limit reached. Retrying with backoff...",
      "details": null
    }
  }
  ```
* **No Unhandled Promise Rejections**: All asynchronous calls must use `async/await` with explicit catch blocks and structured error logging.
