# Reconciliation audit chain (SHA-256)

Every row in `reconciliation_logs` is part of a per-batch hash chain, so a row edited, inserted or deleted directly in the database (outside the app) can be detected.

## Columns

| Column | Meaning |
|---|---|
| `entry_hash` | SHA-256 of `previous_hash` plus the audited fields of this row |
| `previous_hash` | Link hash of the previous row in the same batch, `NULL` for the first row |

Audited fields: `id, batch_id, bank_tx_id, rzp_settlement_id, match_status, match_tier, confidence_score, delta_amount, diagnostic_type, diagnostic_note, matched_at, human_action, created_at`.
`superseded`, `superseded_by_id` and `updated_at` are bookkeeping that the engine flips on old rows, so they are not hashed.

The link hash is a second SHA-256 over only `id, batch_id, bank_tx_id, created_at` and the row's own `previous_hash`. It is kept separate from `entry_hash` on purpose: approve, deny, conflict resolution and batch-approve edit a row in place, so they only re-seal that row's `entry_hash`, and only if the stored row still matched its seal before the edit. A row changed with plain SQL stays flagged even after a later approve or deny. Chain order (`created_at`, strictly increasing per batch) and the links are never rewritten.

Hashes are computed in a SQLAlchemy `before_flush` hook (`app/models/reconciliation_log.py`), so every writer is covered: the reconciliation engine, the manual action endpoints and anything else that adds a `ReconciliationLog`. Values are canonicalised (UTC microsecond timestamps, 2dp decimals) so a hash computed before insert matches the one recomputed from the stored row, on SQLite and PostgreSQL.

## Endpoints

`GET /api/v1/reconciliation/{batch_id}/verify-audit-chain` walks the whole batch (superseded rows included) in O(N), streaming the rows from the database in chunks so memory stays flat.

```json
{ "success": true, "data": { "status": "VERIFIED", "tampered": false, "total_records": 120, "verified_records": 120, "chain_head": "..." } }
```

On the first broken row it stops and reports it:

```json
{ "success": true, "data": { "status": "COMPROMISED", "tampered": true, "total_records": 120, "verified_records": 41,
  "failed_at_id": "<log id>", "expected_hash": "...", "actual_hash": "...", "reason": "ENTRY_HASH_MISMATCH" } }
```

* `ENTRY_HASH_MISMATCH`: a field of `failed_at_id` was changed (`expected_hash` is the recomputed value, `actual_hash` the stored one).
* `BROKEN_CHAIN_LINK`: a row before `failed_at_id` was deleted, inserted or reordered (`expected_hash` is the link the row should carry, `actual_hash` what it carries).

`GET /api/v1/reconciliation/{batch_id}/audit-certificate` downloads a JSON Audit Compliance Certificate containing the verification result, `content_sha256` of the certificate body and, when `AUDIT_SIGNING_KEY` is set, an HMAC-SHA256 `signature` over the same canonical body. Without the key the certificate is unsigned (`"signed": false`). PDF output is not implemented.

## Limits

* The chain is unkeyed SHA-256. Someone who knows the algorithm and has write access can recompute hashes for a row they edit. Store the `chain_head` (or the signed certificate) outside the database at period close to make that visible.
* Deleting the newest rows of a batch cannot be seen from the chain alone; compare `total_records` / `chain_head` with a previously saved value.
* Existing rows are chained by migration `0002` in `created_at, id` order. Run `alembic upgrade head` after pulling.
* On PostgreSQL, writers take a per-batch advisory lock until commit so two concurrent runs cannot fork a chain.
