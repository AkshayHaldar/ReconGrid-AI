# Incremental ledger loading

The dashboard requests one 200-record window initially and requests the next only
near the bottom of the virtualized list or when the user selects **Load more**.
Appending preserves the scroll position. Sorting, searching, diagnostic/status
filters and refresh start a new query generation, cancel the old request and
reset the virtualizer. Late responses cannot replace a newer query. A failed
append leaves existing rows visible and retries the same cursor.

## API compatibility

`GET /api/v1/reconciliation/{batch_id}/records?limit=200` selects cursor mode.
Continue using `cursor=<next_cursor>` and the same query parameters. `limit` is
bounded to 1–200; no cursor on the first request is needed. Existing `page` and
`page_size` clients retain their offset-based behavior when cursor mode is absent.
The default ordering is transaction date descending with log UUID descending as
a unique tie-breaker. Legacy date ordering also gains this stable tie-breaker.

Cursor mode supports `status`, `q`, `diagnostic`, `sort` (`date`, `bank_amount`,
`rzp_amount`, `delta_amount`, `bank_utr`) and `direction` (`asc`, `desc`). Sorting
and filters run before pagination. Missing values sort last; money comparisons
use Decimal and UTR comparisons use lowercase values. A cursor is bound to the
batch, filters and ordering. Reusing it with a different query returns HTTP 400.
Malformed shapes, IDs, dates, versions, non-finite/oversized amounts and oversized
tokens are rejected. Cursors are opaque seek positions, not signed authorization
credentials; every request still applies the batch/filter predicates.

Responses add `has_more` and `next_cursor`. `total_count` is exact on the first
window and null on continuation windows; clients retain the first count. The
legacy mode still returns its existing numeric count. Cursor queries fetch at
most `limit + 1` logs and do not scan past a growing OFFSET or repeat COUNT.
Actual database cost still depends on indexes, filters and join/sort plans;
keyset pagination is not a promise of literal constant-time arbitrary searches.
Inspect PostgreSQL EXPLAIN plans for production-specific tuning.

## Actions and citations

Q&A citations use `anchor_id=<record UUID>` to start a window at the cited row,
even when it has not been loaded. The anchor must belong to the batch/filter or
the API returns 404. The dashboard clears filters for a citation and offers
**Return to first records**. An anchor and continuation cursor cannot be combined.

Conflict resolution loads all candidates for the selected settlement on demand
using the batch/status/`settlement_id` filter, not just currently loaded rows.
Explicit whole-selection batch approval also walks all matching windows
sequentially before selecting high-confidence suggestions. These user-invoked
actions can materialize their selection; ordinary scrolling does not fetch the
whole batch or fan out page requests. Existing amount/approval/export logic is
preserved. Two pre-existing export type errors are repaired by accepting Sequence
and explicitly retaining the existing skip for records without settlements.

The CSV review follow-up prefixes an apostrophe to text cells beginning with
spreadsheet formula/control prefixes (including formulas after leading whitespace
or a BOM). It does not alter stored records, dates, or formatted numeric amounts;
negative monetary values remain numeric CSV cells.

This is a live ledger, not an MVCC snapshot spanning HTTP requests. Insertions
before a cursor do not shift existing rows between windows. Updates/deletions can
change membership or counts; refresh starts a fresh traversal. Mutations refresh
the visible query. No financial amounts are recomputed by the paging layer.

## Validation

Run `pytest` from backend, and `npm test`, `npx tsc --noEmit`, `npm run lint` and
`npm run build` from frontend. The API tests cover all sort directions, tied/null
values, malformed/query-mismatched cursors, legacy compatibility, candidates,
anchors and seek SQL. The pager tests execute the real TypeScript modules with
the network boundary replaced to test races, cancellation, retries and bounds.

Manual verification used 20,201 synthetic SQLite rows: 200 initially loaded,
automatic continuation, unchanged scroll offset on append, reset on sort,
search for an initially unloaded row, and all 201 competing settlement claimants.
Desktop and 390px layouts were checked. A local one-shot sample returned 200 rows
at the first, 10,000 and 19,000 positions (48.60/23.38/22.52ms respectively); these
are environment observations, not a performance SLA or PostgreSQL benchmark.
No customer data or live gateway/LLM credentials were used.
