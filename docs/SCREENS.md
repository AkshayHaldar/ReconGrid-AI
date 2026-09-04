# Screen & State Inventory: Razorpay ReconGrid AI

This inventory catalogs every visual surface, modal, drawer, interactive element, and transient state across the ReconGrid AI frontend.

---

## 1. Top-Level Surface: Main Reconciliation Dashboard

- **Route**: `/` (Next.js App Router: `frontend/src/app/page.tsx`)
- **Component File**: `frontend/src/app/page.tsx`
- **Primary User Role**: Finance Controller / Chartered Accountant / Merchant Operations Lead
- **User Intent**: Review total reconciliation status for the current billing cycle, identify variances and exceptions, review suggested matches, resolve multi-candidate conflicts, and export audited statements.

### Sub-Surfaces & Section Breakdown

#### 1.1 Header & Control Strip (`Header.tsx`)
- **File**: `frontend/src/components/Header.tsx`
- **Elements**:
  - Brand identity icon ("RG" monogram) and product title.
  - Track / Gateway indicator badge (`Track 04 • Razorpay`).
  - Fiscal period badge (`Aug 2026 Close (FY 26-27)`).
  - Bank Account selector dropdown (`All Bank Accounts`, `HDFC **4019`, `ICICI **9122`, `SBI **3301`, `AXIS **7712`).
  - Primary Action CTA: `Upload CSV` (opens `UploadModal`).
  - Secondary Action CTA: `Sync / Seed` (opens `DemoSyncModal`).
  - Assistant Trigger: `Ask AI [?]` (toggles `SettlementQaPanel`).
- **Data Dependencies**: Client-side state in `page.tsx`.

#### 1.2 Summary KPI Cards & Trial Balance Strip (`SummaryCards.tsx`)
- **File**: `frontend/src/components/SummaryCards.tsx`
- **Elements**:
  - **Metric 1: Total Ingested Ledger**: Total statement rows, gross bank statement INR value, 100% ingestion badge.
  - **Metric 2: Auto-Reconciled Net**: Match rate percentage (`94.8%`), reconciled INR value, progress bar, matched txn count. Clickable (filters table to `MATCHED`).
  - **Metric 3: CA Review Required**: Suggested + Conflict count, quick status badge. Clickable (filters table to `SUGGESTED` or `CONFLICT`).
  - **Metric 4: Unresolved Variance**: Exception count and net unresolved INR discrepancy. Clickable (filters table to `EXCEPTION`).
  - **Trial Balance Reconciliation Control Strip**: Mathematical identity statement (`Ingested = Reconciled + Exceptions`), zero-variance badge / variance warning alert.
- **Data Dependencies**: `GET /api/v1/reconciliation/status`.

#### 1.3 Filter & Action Bar (`FilterBar.tsx`)
- **File**: `frontend/src/components/FilterBar.tsx`
- **Elements**:
  - Primary Status Tabs: `All Records [1]`, `Matched [2]`, `Suggested [3]`, `Conflicts [4]`, `Exceptions [5]`.
  - Diagnostic Dropdown: Filter by `FEE_DEDUCTION`, `TDS_194O_DEDUCTION`, `BATCHED_SETTLEMENT`, `REFUND_ADJUSTED`, `FX_ADJUSTED`, `REVERSAL`, `UNRESOLVED`.
  - Search Input: Real-time filter across UTR, Settlement ID, and bank narrative (`/` keyboard shortcut).
  - Batch Approval Button: `Batch Approve (≥90%)` (visible when suggestions exist or on Suggested tab).
  - Export CSV Button: Triggers `GET /api/v1/reconciliation/export/csv`.
- **Data Dependencies**: `ReconciliationStatus`, local filter handlers in `page.tsx`.

#### 1.4 Reconciliation Ledger Grid (`ReconciliationTable.tsx`)
- **File**: `frontend/src/components/ReconciliationTable.tsx`
- **Columns**:
  1. `Date` (DD Mon YYYY format, tabular numbers).
  2. `Bank UTR / Narrative` (UTR with one-click copy button, truncated bank description with hover tooltip).
  3. `Bank Amt` (CR in emerald / DR in rose with badge, tabular INR).
  4. `RZP Settlement ID` (Settlement ID with one-click copy button).
  5. `RZP Net (Gross)` (Net payout + Gross transaction amount breakdown).
  6. `Delta` (Exact variance amount in INR, color-coded by diagnostic type).
  7. `Status & Diagnostic` (Interactive `StatusBadge` with tooltip popover).
  8. `Actions` (Approve/Deny for suggestions, Resolve for conflicts, Audit for exceptions, "AUTO OK" for matched).
- **Data Dependencies**: `GET /api/v1/reconciliation/records`.

---

## 2. Modal & Drawer Inventory

### 2.1 Bank Statement Ingestion Modal (`UploadModal.tsx`)
- **File**: `frontend/src/components/UploadModal.tsx`
- **Trigger**: Header `Upload CSV` button or Summary Card empty state CTA.
- **Layout**: Centered modal overlay (`fixed inset-0 flex items-center justify-center`).
- **Interactive Elements**:
  - Drag-and-drop file upload zone (supports `.csv`, `.pdf`).
  - File details card (filename, size, parser badge: "Multi-Page PDF Engine" / "Streaming CSV Parser").
  - PDF Password input with reveal toggle (`Eye`/`EyeOff`).
  - Expandable Bank Password Formula Guide (HDFC, ICICI, SBI, Axis, Kotak, PNB, BOB, Canara cheat sheets).
  - Sample test statement download buttons (HDFC, ICICI, SBI).
  - Inline error alert box with itemized row-level validation errors.
  - Action buttons: `Cancel` and `Upload & Reconcile` (with loading spinner).
- **Data Dependencies**: `POST /api/v1/bank/upload`, `GET /api/v1/bank/password-hints`.

### 2.2 Synthetic Data & Razorpay Sync Modal (`DemoSyncModal.tsx`)
- **File**: `frontend/src/components/DemoSyncModal.tsx`
- **Trigger**: Header `Sync / Seed` button.
- **Layout**: Centered modal overlay.
- **Interactive Elements**:
  - Action Card 1: `Seed 60 Golden Test Transactions` (generates full spectrum of edge cases).
  - Action Card 2: `Pull Settlements via Razorpay REST API` (triggers live/mock gateway sync).
  - Success banner displaying ingested and reconciled record counts.
  - Close button.
- **Data Dependencies**: `POST /api/v1/demo/seed`, `POST /api/v1/razorpay/sync`.

### 2.3 Multi-Candidate Conflict Resolution Drawer (`ConflictDrawer.tsx`)
- **File**: `frontend/src/components/ConflictDrawer.tsx`
- **Trigger**: Clicking `Resolve` or `CONFLICT` badge on a conflicted record row.
- **Layout**: Centered modal dialog with warm amber border styling.
- **Interactive Elements**:
  - Contested Razorpay Settlement breakdown (Gross, Fee, GST, Net).
  - Active Bank Statement row details (Date, UTR, Amount, Narrative).
  - List of competing bank statement rows locking the settlement.
  - Automatic displacement informational callout (`AUTO_DISPLACED` explanation).
  - CA Resolution Audit Note text input field.
  - Action Buttons: `Dismiss / Mark Exception` (unlinks settlement) and `Assign & Resolve` (allocates settlement and unlocks competing rows).
- **Data Dependencies**: `POST /api/v1/reconciliation/resolve-conflict`.

### 2.4 Forensic Audit Exception Inspector (`ExceptionDrawer.tsx`)
- **File**: `frontend/src/components/ExceptionDrawer.tsx`
- **Trigger**: Clicking `Audit` or `EXCEPTION` badge on an exception row.
- **Layout**: Centered wide modal dialog with rose border styling.
- **Interactive Elements**:
  - Audit Diagnostic Note banner (root-cause explanation).
  - Side-by-Side Raw Payloads:
    - Left Card: Bank Statement CSV Raw Data + JSON viewer + `Copy JSON` button.
    - Right Card: Linked Razorpay Settlement Data + JSON viewer + `Copy JSON` button.
  - Close button.
- **Data Dependencies**: Record item details passed as prop.

### 2.5 Settlement Q&A Slide-Out Assistant (`SettlementQaPanel.tsx`)
- **File**: `frontend/src/components/SettlementQaPanel.tsx`
- **Trigger**: Header `Ask AI [?]` button, keyboard shortcut `?`, or contextual jump link.
- **Layout**: Right-aligned slide-out drawer (`fixed inset-y-0 right-0 w-full sm:w-[460px]`).
- **Interactive Elements**:
  - Header with context memory indicator and `Clear Chat` / `Close` buttons.
  - Multi-Chat Tab Bar (`Chat 1`, `Chat 2`, `+ New Tab`) for independent inquiry sessions.
  - Categorized prompt chips (All Inquiries, KPIs & Dashboard, GST & Tax, Recon & Batches, CA & Audits).
  - Conversation message stream (User query bubble, Agent answer bubble).
  - Source Record Citation Link: `View source record →` (triggers auto-scroll and highlight on table row).
  - Numeric Guardrail Verification Badge: `Guardrail OK`.
  - Natural-language query input box + Send button.
- **Data Dependencies**: `POST /api/v1/qa/ask`.

---

## 3. Transient & Micro-Interaction States

| State | Visual Treatment | Trigger | Exit Condition |
|---|---|---|---|
| **Table Loading** | Centered blue pulsing spinner + text: `"Running deterministic 4-tier reconciliation engine..."` | Initial page mount, tab filter switch, upload/sync finish | API response received |
| **Table Empty** | Muted box + text: `"No reconciliation records match the selected filter criteria."` | Query/filter yields 0 matching rows | Filter changed or data re-seeded |
| **Record Highlighted** | Blue pulsing glow (`citation-highlight` animation: `bg-blue-950/40 ring-1 ring-blue-500`) | Clicking `"View source record"` in Q&A panel | 3-second CSS animation decay |
| **UTR/ID Copied** | Copy icon toggles to emerald double-check (`CheckCheck`) | Clicking copy button next to UTR or Settlement ID | 1.5-second `setTimeout` reset |
| **Status Popover** | Floating black card with diagnostic type, tier, note, and confidence score | Hovering over `StatusBadge` in table row | Mouse leave |
| **Batch Approving** | Button disabled with text: `"Approving..."` | Clicking `"Batch Approve (≥90%)"` | Batch approval API call finishes |
| **Upload Password Error** | Red error container with password hints auto-expanded and focus set to password input | Uploading a password-protected PDF without password | User supplies password and re-submits |
| **Keyboard Nav (1-5, /, ?)** | Focus shifted to search box (`/`), tab switched (`1-5`), or Q&A opened (`?`) | Global keydown listener | Key released / Blur |

---

## 4. Visual & Structural Inconsistencies Identified

1. **Drawer vs Modal Identity Crisis**: `ConflictDrawer` and `ExceptionDrawer` are named "Drawer" but implemented as centered dialog modals. Meanwhile, `SettlementQaPanel` is an actual side drawer. This causes jarring mental context switches for the operator.
2. **Dense Popover Collision Risk**: The hover popover on `StatusBadge` is positioned `bottom-full left-1/2` with fixed pixel width (`w-64`), which gets clipped or causes horizontal overflow on edge columns and mobile screens.
3. **Double Header Visual Clutter**: The header has redundant elements between mobile and desktop (e.g. fiscal period duplicated in two distinct responsive blocks), adding DOM complexity.
4. **Hardcoded Monolithic Layout**: Everything lives in a single page without sub-views for Period Close, GST Tax Ledgers, or Batch Management.
