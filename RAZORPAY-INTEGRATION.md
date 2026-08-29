# 💳 Razorpay Integration Guide — ReconGrid AI

This guide covers everything needed to connect ReconGrid AI to Razorpay in **Test Mode**, generate test transactions, and reconcile settlements.

> ⚠️ **Test Mode Only:** This is a verification/defense tool — no real payments are collected. All keys used should be `rzp_test_` keys.

---

## 1. Setting Up Your Razorpay Test Account

1. Log into your [Razorpay Dashboard](https://dashboard.razorpay.com/)
2. Switch to **Test Mode** (toggle in the top-left corner)
3. Go to **Settings → API Keys → Generate Key**
   - You'll get a `Key ID` (starts with `rzp_test_`) and a `Key Secret`
4. Go to **Settings → Webhooks → Add New Webhook**
   - URL: your ngrok or server URL (e.g., `https://your-domain.ngrok-free.app/api/v1/webhooks/razorpay`)
   - Secret: enter a strong secret (this is your `webhook_secret`)
   - Events: check `settlement.processed`, `payment.captured`, `refund.processed`
5. Put all three keys in your `backend/.env`:

```env
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxx
RAZORPAY_KEY_SECRET=your_key_secret_here
RAZORPAY_WEBHOOK_SECRET=your_webhook_secret_here
```

---

## 2. Razorpay Entity IDs (Quick Reference)

When looking at data or writing tests, these prefixes identify entity types:

| Prefix | Entity | Example |
|---|---|---|
| `order_` | Order | `order_EKfwwad3rK6m98` |
| `pay_` | Payment | `pay_EKfwwad3rK6m99` |
| `rfnd_` | Refund | `rfnd_EKfwwad3rK6m00` |
| `setl_` | Settlement | `setl_EKfwwad3rK6m01` |
| `cust_` | Customer | `cust_EKfwwad3rK6m02` |

---

## 3. Generating Test Transactions

To test reconciliation, you need transactions in your Razorpay test account.

### Recommended: Run the Seed Script

```bash
cd backend
python scripts/seed_test_transactions.py --count 60
```

This creates synthetic orders and auto-captures them in your Razorpay test account in a few minutes, giving you realistic data to reconcile against.

---

## 4. API Endpoints Used

All Razorpay API calls go through `app/services/razorpay_client.py` using HTTP Basic Auth (`Key ID` + `Key Secret`):

| Purpose | Endpoint | Notes |
|---|---|---|
| Fetch settlements | `GET /v1/settlements` | Primary data source for reconciliation (cursor-paginated) |
| Fetch settlement by ID | `GET /v1/settlements/{id}` | Used when a webhook references a new settlement |
| Fetch refunds | `GET /v1/refunds` | Used by Tier 3 diagnostics to explain refund deltas |
| Fetch payment details | `GET /v1/payments/{id}` | Enriches settlement rows with customer/method info |
| Create order | `POST /v1/orders` | Used by the seed script (amount is in **paise**: ₹100 = `10000`) |
| Capture payment | `POST /v1/payments/{id}/capture` | Used by the seed script |

> ⚠️ **Common Bug Alert:** Razorpay amounts are always in **paise** (1 INR = 100 paise). The codebase handles this conversion in `app/utils/money.py` — never multiply or divide by 100 manually in route handlers.

---

## 5. Webhook Setup & Security

### Why Webhook Security Matters
Anyone on the internet can send a `POST` request to your webhook URL. Without signature verification, an attacker could inject fake settlement events and corrupt your reconciliation ledger.

### How We Verify Signatures (in `app/core/security.py`)

```python
import hmac
import hashlib

def verify_razorpay_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    """
    Verifies that the webhook request came from Razorpay.
    Uses HMAC-SHA256 over the RAW request bytes (before JSON parsing)
    and a constant-time comparison to prevent timing attacks.
    """
    expected = hmac.new(
        key=secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
```

This runs as a FastAPI dependency **before** the request body is parsed as JSON. An invalid signature returns `400 Bad Request` and never touches any business logic.

---

## 6. Error Handling & Rate Limits

| Response from Razorpay | What It Means | How ReconGrid Handles It |
|---|---|---|
| `400 Bad Request` | Invalid parameters | Fails fast, logs error, does not retry |
| `401 Unauthorized` | Bad or rotated API key | Fails immediately and alerts operator (won't self-resolve) |
| `429 Too Many Requests` | Hit rate limit | Exponential backoff + jitter, retries up to 5 times |
| `500/502/503/504` | Razorpay server issue | Retries with backoff (transient failure) |

---

## 7. Moving from Test to Production (Checklist)

When you're ready to use live keys:

- [ ] Replace `rzp_test_` keys with live keys in your production `.env` (no code changes needed)
- [ ] Add your production HTTPS URL in the Razorpay Webhooks dashboard
- [ ] Copy the **live** webhook secret to `RAZORPAY_WEBHOOK_SECRET`
- [ ] Confirm all amounts are tested with real paise-to-rupee conversions
- [ ] Run a test reconciliation batch with a small real settlement to verify
