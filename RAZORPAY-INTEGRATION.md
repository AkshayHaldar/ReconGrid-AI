# ReconGrid AI — Razorpay Integration Guide

This document covers everything needed to connect ReconGrid AI to Razorpay in **test mode**, generate realistic synthetic transaction data, and consume settlement/refund data for reconciliation. Everything here uses **test-mode keys only** — this is a defense/verification tool, not a payment-initiation product, so production payment collection is explicitly out of scope.

---

## 1. Account & Key Setup

1. Create a Razorpay account → switch dashboard to **Test Mode** (toggle, top-left).
2. **Settings → API Keys → Generate Test Key** → gives you `key_id` (public) and `key_secret` (private).
3. **Settings → Webhooks → Add New Webhook** → gives you a separate `webhook_secret`. This is a **different secret from `key_secret`** — a common integration bug is using the wrong one for HMAC verification.
4. Store all three in your backend `.env` (never the frontend):
   ```
   RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxx
   RAZORPAY_KEY_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
   RAZORPAY_WEBHOOK_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
   ```
5. Auth on every REST call is **HTTP Basic Auth**: `key_id` as username, `key_secret` as password.

---

## 2. Entity ID Reference (so your parser/matcher recognizes them)

| Prefix | Entity |
|---|---|
| `order_` | Order |
| `pay_` | Payment |
| `rfnd_` | Refund |
| `setl_` | Settlement |
| `cust_` | Customer |

Your ingestion/matching code should validate these prefixes when parsing IDs from webhook payloads or API responses — an ID without the expected prefix is a signal of a malformed or forged payload.

---

## 3. Generating Synthetic Test Transactions (to reconcile against)

You cannot reconcile against an empty test account — you need real (test-mode) payments flowing through Razorpay first. Two options:

### Option A — Orders API + Test Checkout (recommended for a realistic demo)
1. Backend creates an order:
   ```
   POST /v1/orders
   { "amount": 500000, "currency": "INR", "receipt": "recon_test_001" }
   ```
   (`amount` is in **paise** — 500000 = ₹5,000.00. This is the single most common integration bug: forgetting the ×100.)
2. Frontend loads Razorpay Checkout with the returned `order_id` and completes payment using [Razorpay's published test card/UPI credentials](https://razorpay.com/docs/payments/payments/test-card-upi-details/) (test mode only — no real money moves).
3. Payment lands as `payment.captured`; settlements accrue on Razorpay's normal test-mode settlement cycle and become fetchable via the Settlements API.

### Option B — Seed Script (faster for hackathon iteration, no UI needed)
Write a `scripts/seed_test_transactions.py` that calls `POST /v1/orders` then `POST /v1/payments/{id}/capture` directly against test-mode auto-capture-eligible test payment methods, in a loop, to generate a batch (e.g., 50–100 synthetic transactions) in minutes rather than manually clicking through Checkout each time. This is the batch your 50+ record test set (Track 04 requirement) should be built from — **label it explicitly as synthetic** in your submission, since Razorpay's test settlements don't perfectly mirror live settlement timing.

---

## 4. Core Endpoints Used

| Purpose | Endpoint | Notes |
|---|---|---|
| Create order | `POST /v1/orders` | Amount in paise. Idempotent via `Idempotency-Key` header. |
| Capture payment | `POST /v1/payments/{id}/capture` | Only for `authorized` payments not on auto-capture. |
| Fetch payment | `GET /v1/payments/{id}` | Use to enrich a settlement row with method/customer context. |
| Create refund | `POST /v1/payments/{id}/refund` | Full or partial (`amount` param). |
| Fetch refunds | `GET /v1/refunds` , `GET /v1/payments/{id}/refunds` | Used by Tier 3 diagnostics to explain refund-adjusted deltas. |
| Fetch settlements | `GET /v1/settlements` | Cursor-paginated (`count`, `skip`); this is your primary reconciliation data source. |
| Fetch settlement by ID | `GET /v1/settlements/{id}` | Used when a webhook references a settlement not yet in your local cache. |
| Instant settlement (optional) | `POST /v1/settlements/ondemand` | Only relevant if demoing near-real-time settlement cycles; not required for core reconciliation. |

All calls go through the `RazorpayClient` service (see `ARCHITECTURE.md` §2.2) — never called ad hoc from route handlers.

---

## 5. Webhook Integration

### 5.1 Events to Subscribe To
* `settlement.processed` — primary trigger for reconciliation runs.
* `payment.captured` / `payment.failed` — useful for the seed/demo flow and for detecting payments Razorpay knows about that haven't settled yet.
* `refund.processed` — feeds Tier 3 refund-adjustment diagnostics without waiting for a full settlement fetch.

### 5.2 Local Testing
Razorpay needs a public HTTPS URL to deliver webhooks to. For local dev, tunnel your FastAPI server (e.g., `ngrok http 8000`) and register the tunnel URL under **Settings → Webhooks** in test mode. Do not leave a stale ngrok URL registered after a session ends — Razorpay will retry delivery against a dead endpoint and clutter your dashboard's webhook logs.

### 5.3 Signature Verification (Python, mandatory before any parsing)
```python
import hmac
import hashlib
from fastapi import Request, HTTPException

def verify_razorpay_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(
        key=secret.encode(),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

async def razorpay_webhook_guard(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not signature or not verify_razorpay_signature(raw_body, signature, settings.RAZORPAY_WEBHOOK_SECRET):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    return raw_body
```
This runs as a FastAPI dependency **before** the route body is parsed as JSON — an invalid signature never reaches business logic.

### 5.4 Delivery Guarantees (design around these, don't assume otherwise)
* Razorpay retries webhook delivery on non-2xx response, with backoff, for a limited retry window — **your endpoint must return `200` quickly** (verify + enqueue + return, don't do the full reconciliation synchronously in the request handler) or you'll get duplicate deliveries.
* Delivery order is **not guaranteed**. A `settlement.processed` event can arrive before your bank CSV for that period is uploaded. Design for `PENDING_BANK_DATA`, not "unexpected event."
* Dedupe on the payload's own event identifier (present in the webhook body) before taking any action — store processed event IDs with a unique constraint (see `ARCHITECTURE.md §2.2`).

---

## 6. Error Handling Matrix

| Razorpay Error Type | Meaning | ReconGrid Handling |
|---|---|---|
| `BAD_REQUEST_ERROR` | Invalid params (e.g., bad amount format) | Fail fast, log input, do not retry |
| `GATEWAY_ERROR` | Upstream processor issue | Retry with backoff (transient) |
| `SERVER_ERROR` | Razorpay-side failure | Retry with backoff, alert if retry ceiling hit |
| HTTP `429` | Rate limited | Exponential backoff + jitter, respect `Retry-After` if present |
| HTTP `401` | Bad/rotated key | Do **not** retry — alert immediately, this won't self-resolve |

---

## 7. Rate Limits & Backoff
Razorpay enforces API rate limits that can vary by endpoint and account tier — don't hardcode a specific numeric assumption in code. Instead:
* Always implement exponential backoff + jitter on `429` regardless of the exact limit.
* Respect a `Retry-After` header if returned.
* Cap total retries (see `ARCHITECTURE.md §5`) so a sustained limit breach fails loudly instead of looping forever.

---

## 8. Sandbox → Production Checklist (for the write-up, even if you don't flip this switch during the hackathon)
- [ ] Swap `rzp_test_` keys for live keys via environment variable only — no code change required.
- [ ] Re-register webhook URL against the production HTTPS endpoint.
- [ ] Re-verify webhook secret is the **live-mode** webhook secret, not the test one.
- [ ] Confirm `Idempotency-Key` usage on all POST calls that create financial state (orders, refunds).
- [ ] Load-test the webhook endpoint's fast-ack path before relying on it in production.
