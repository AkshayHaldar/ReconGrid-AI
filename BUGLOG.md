# Bug Log

Kept live during the build, per `WORKFLOW-RULES.md` §7. This feeds Question 12 ("What broke, and how you got out") directly — write entries the day the bug happens, not reconstructed from memory the night before submission.

Format:
```
## [YYYY-MM-DD] [component] Short title
- **Broke**: what actually happened, observed behavior
- **Root cause**: the real reason, not the symptom
- **Fix**: what changed
- **Time lost**: rough hours
```

---

## [2026-08-26] [diagnostics] Reversal debits classified as exact credit matches
- **Broke**: Settlement reversal and chargeback debit rows were matching exact positive payouts due to absolute amount matching evaluated before direction checks.
- **Root cause**: `DiagnosticsService.evaluate_delta` had `is_amount_matching` check before `bank_tx.direction == "DEBIT"`.
- **Fix**: Re-ordered evaluation pipeline to classify `DEBIT` direction reversals first with `REVERSAL` diagnostic type.
- **Time lost**: ~15 minutes.

---

## [2026-08-26] [database] Decimal and datetime serialization in SQLAlchemy SQLite JSON columns
- **Broke**: Ingestion and demo seed failed on SQLite `raw_csv_row` and `raw_payload` with `TypeError: Object of type Decimal is not JSON serializable`.
- **Root cause**: Python `json.dumps` does not natively serialize `Decimal` or `datetime` objects in SQLAlchemy JSON columns without a custom serializer.
- **Fix**: Configured custom `json_serializer` in `database.py` mapping `Decimal` to string and `datetime`/`date` to ISO formatted strings.
- **Time lost**: ~15 minutes.

---

## [2026-08-26] [qa_agent] Natural language query stop-word collision in Q&A retrieval
- **Broke**: Query `"Why did order #9999999999 not settle?"` matched order records despite nonexistent ID because word `"order"` matched description tokens.
- **Root cause**: Token extraction didn't filter English stop words and broad nouns.
- **Fix**: Enhanced token extractor in `qa_repo.py` to filter stop words and prioritize tokens containing digits or gateway-specific entity prefixes (`setl_`, `CMS`, `RTGS`, `ICIC`, `SBI`).
- **Time lost**: ~15 minutes.

---

## [2026-08-29] [reconciliation] Offset-naive and offset-aware datetime subtraction in Tier 0 fallback & batched matching
- **Broke**: Uploading CSV statements with naive datetime entries caused `TypeError: can't subtract offset-naive and offset-aware datetimes` when calculating delta window against UTC-aware Razorpay timestamps.
- **Root cause**: `(bank_tx.date - s.settlement_created_at).total_seconds()` attempted direct subtraction when one operand had `tzinfo=None` and the other had `tzinfo=timezone.utc`.
- **Fix**: Created `_diff_seconds` helper in `reconciliation.py` that normalizes naive datetimes to UTC before evaluating time difference.
- **Time lost**: ~10 minutes.

---

## [2026-08-29] [reconciliation] Multi-candidate conflict resolution left competing claimants locked or double-allocated
- **Broke**: When multiple bank statement rows contested the same Razorpay settlement, manually resolving one bank row in the UI left competing bank rows in `CONFLICT` state or allowed double-credit.
- **Root cause**: The conflict resolution endpoint updated only the targeted record without evaluating or displacing other locked claimants in the batch.
- **Fix**: Added `get_competing_conflict_logs` repository query and updated `/resolve-conflict` API to automatically unlock and transition competing bank rows to `EXCEPTION` with `human_action = "AUTO_DISPLACED"` and explicit audit notes.
- **Time lost**: ~20 minutes.
