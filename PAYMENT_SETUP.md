# Payment Gateway — Setup & Integration Guide

This document covers everything needed to understand, run, and eventually replace the **mock payment gateway** that ships with this project.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture — Two-Phase Commit](#2-architecture--two-phase-commit)
3. [Database — payment_orders Table](#3-database--payment_orders-table)
4. [API Reference](#4-api-reference)
   - [POST /payments/initiate](#41-post-paymentsinitiate)
   - [POST /payments/verify](#42-post-paymentsverify)
   - [GET /payments/order/{order_id}](#43-get-paymentsorderorder_id)
5. [How the Mock Signature Works](#5-how-the-mock-signature-works)
6. [Frontend Integration (Mock)](#6-frontend-integration-mock)
7. [Frontend Integration (React / Axios example)](#7-frontend-integration-react--axios-example)
8. [Testing with curl / Postman](#8-testing-with-curl--postman)
9. [Error Reference](#9-error-reference)
10. [Migrating to Real Razorpay](#10-migrating-to-real-razorpay)
11. [Migrating to Stripe](#11-migrating-to-stripe)
12. [Security Notes](#12-security-notes)
13. [File Map](#13-file-map)

---

## 1. Overview

Money flow in this platform:

```
User clicks "Donate"
        │
        ▼
POST /payments/initiate        ← creates PaymentOrder (status = pending)
        │                         returns order_id + mock credentials
        │
  [Payment Modal shown]        ← mock: skip modal, use returned credentials
        │
        ▼
POST /payments/verify          ← verifies HMAC signature
        │                         creates Donation row atomically
        │                         marks PaymentOrder as paid
        ▼
  Donation confirmed ✓
  campaign.raised_amount incremented (atomic SQL UPDATE)
  Email sent to anonymous donor (if applicable)
```

**Key design decision — why two separate calls?**

The `Donation` row is created **only after** a verified payment. This prevents phantom donations (records with no money behind them) which is a common bug in naive implementations where the donation is inserted on button click.

---

## 2. Architecture — Two-Phase Commit

### Phase 1 — Initiate

| What happens | Detail |
|---|---|
| Validates campaign is `active` | 404 if not |
| Validates milestone belongs to campaign and is `active` | 400 if locked/completed |
| Encrypts anonymous email (Fernet) | Stored in `payment_orders.anonymous_email` |
| Generates `order_id` | `MOCK_ORDER_<12 hex>` |
| Generates `payment_id` (mock only) | `MOCK_PAY_<12 hex>` |
| Computes HMAC signature (mock only) | See §5 |
| Inserts `PaymentOrder` with `status=pending` | Expires in **15 minutes** |
| Returns credentials to frontend | `order_id`, `mock_payment_id`, `mock_signature` |

### Phase 2 — Verify

| What happens | Detail |
|---|---|
| Fetches `PaymentOrder` by `order_id` | 404 if not found |
| Checks `status` is `pending` | 400 if already paid or failed |
| Checks `expires_at` | Marks failed + 400 if expired |
| Verifies HMAC signature (timing-safe `hmac.compare_digest`) | 400 on mismatch |
| Cross-checks `payment_id` matches stored value (mock only) | 400 on mismatch |
| Re-validates campaign still `active` | Marks order failed + 400 if not |
| Inserts `Donation` row | Via `db.flush()` to get ID before committing |
| Atomically increments `Campaign.raised_amount` | SQL `UPDATE … SET raised_amount = raised_amount + ?` (no race condition) |
| Marks `PaymentOrder.status = paid`, links `donation_id` | Single `db.commit()` |
| Decrypts + sends email to anonymous donor | Non-fatal — donation already committed |
| Inserts `EmailNotification` for proof-upload alerts | For anonymous donors |

---

## 3. Database — payment_orders Table

Run the migration before starting the server:

```bash
# Activate your virtualenv first
source .venv/bin/activate

alembic upgrade head
```

### Schema

| Column | Type | Description |
|---|---|---|
| `id` | Integer PK | Auto-increment |
| `user_id` | FK → users.id | `NULL` for anonymous donations |
| `campaign_id` | FK → campaigns.id | Target campaign |
| `milestone_id` | FK → milestones.id | Target milestone |
| `donation_id` | FK → donations.id | Filled after successful verify |
| `amount` | Float | In INR, max ₹10,00,000 |
| `is_anonymous` | Boolean | Whether donor is anonymous |
| `anonymous_email` | Text | Fernet-encrypted email (if provided) |
| `order_id` | String(64) UNIQUE | `MOCK_ORDER_…` / `order_…` (Razorpay) |
| `payment_id` | String(64) | `MOCK_PAY_…` / `pay_…` (Razorpay) |
| `gateway` | String(32) | `"mock"` \| `"razorpay"` \| `"stripe"` |
| `status` | String(16) | `pending` → `paid` or `failed` |
| `expires_at` | DateTime | 15 min after creation (UTC, naive) |
| `created_at` | DateTime(tz) | Server default `now()` |
| `updated_at` | DateTime(tz) | Auto-updated on change |

### Status lifecycle

```
pending ──────────────────► paid
   │                          ▲
   │  (expired / campaign      │
   │   deactivated)            │ (verify success)
   └──────────────► failed ───┘
                    (terminal)
```

---

## 4. API Reference

All endpoints require a valid JWT `Authorization: Bearer <token>` header.

---

### 4.1 POST /payments/initiate

Creates a pending payment order and returns the credentials needed for Phase 2.

**Request body**

```json
{
  "campaign_id":  1,
  "milestone_id": 2,
  "amount":       500.00,
  "is_anonymous": false,
  "email":        null
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `campaign_id` | int | Yes | Must be an active campaign |
| `milestone_id` | int | Yes | Must belong to campaign and be `active` |
| `amount` | float | Yes | `> 0`, max `1000000` (₹10 lakh) |
| `is_anonymous` | bool | No | Default `false` |
| `email` | string | No | Required only if `is_anonymous=true` AND donor wants a receipt |

**Success response — 200**

```json
{
  "order_id":        "MOCK_ORDER_A3F8BC2E91D4",
  "amount":          500.00,
  "currency":        "INR",
  "gateway":         "mock",
  "key":             "mock_key",
  "description":     "Donation to 'Save the Forest' — Phase 1: Sapling Planting",
  "mock_payment_id": "MOCK_PAY_9C1D2E3F4A5B",
  "mock_signature":  "e3b0c44298fc1c149afb...sha256hex..."
}
```

> **Note:** `mock_payment_id` and `mock_signature` are **only present when `gateway = "mock"`**.  
> With real Razorpay/Stripe these fields will not exist — the SDK returns them via callback.

---

### 4.2 POST /payments/verify

Verifies the payment and creates the `Donation` record.

**Request body**

```json
{
  "order_id":   "MOCK_ORDER_A3F8BC2E91D4",
  "payment_id": "MOCK_PAY_9C1D2E3F4A5B",
  "signature":  "e3b0c44298fc1c149afb...sha256hex..."
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `order_id` | string | Yes | From initiate response |
| `payment_id` | string | Yes | From initiate response (mock) or Razorpay SDK callback |
| `signature` | string | Yes | From initiate response (mock) or Razorpay SDK callback |

**Success response — 200**

```json
{
  "message":        "Payment successful. Donation recorded.",
  "transaction_id": "TXN-B1C2D3E4F5A6",
  "amount":         500.00,
  "campaign":       "Save the Forest",
  "milestone":      "Phase 1: Sapling Planting"
}
```

Save `transaction_id` — the donor can use it to track their donation at:
```
GET /donations/{transaction_id}   (public, no login required)
```

---

### 4.3 GET /payments/order/{order_id}

Check the status of a payment order.

**Response**

```json
{
  "order_id":       "MOCK_ORDER_A3F8BC2E91D4",
  "status":         "paid",
  "amount":         500.00,
  "gateway":        "mock",
  "expires_at":     "2026-03-12T10:30:00",
  "transaction_id": "TXN-B1C2D3E4F5A6"
}
```

`status` values: `pending` | `paid` | `failed` | `expired`  
`transaction_id` is `null` if status is not `paid`.

---

## 5. How the Mock Signature Works

The mock uses **HMAC-SHA256** — the exact same algorithm Razorpay uses.

```
signature = HMAC-SHA256(
    message = "{order_id}|{payment_id}",
    key     = JWT_SECRET   ← from .env
)
```

**Python equivalent:**
```python
import hashlib, hmac

signature = hmac.new(
    JWT_SECRET.encode(),
    f"{order_id}|{payment_id}".encode(),
    hashlib.sha256
).hexdigest()
```

**When you switch to Razorpay**, the only change is:
- `key` → `RAZORPAY_KEY_SECRET` (from Razorpay dashboard)
- `order_id` → Razorpay's `razorpay_order_id`
- `payment_id` → Razorpay's `razorpay_payment_id`
- `signature` → Razorpay's `razorpay_signature`

The backend verify logic stays **byte-for-byte identical**.

---

## 6. Frontend Integration (Mock)

The mock gateway requires **no real payment modal** — the `initiate` response already contains everything needed for `verify`. This lets you build and test the full payment UI without any Razorpay account.

```
1. User fills donation form (campaign, milestone, amount, anonymous?)
2. Call POST /payments/initiate
3. Store { order_id, mock_payment_id, mock_signature } from response
4. (Optional) Show a fake "Processing Payment…" UI for 1-2 seconds
5. Call POST /payments/verify using those stored values
6. Show success screen with transaction_id
```

---

## 7. Frontend Integration (React / Axios example)

```javascript
// paymentService.js

const API_BASE = process.env.REACT_APP_API_URL; // e.g. http://localhost:8000

/**
 * Step 1 — Initiate payment
 */
export async function initiatePayment({ campaignId, milestoneId, amount, isAnonymous, email }) {
  const res = await axios.post(
    `${API_BASE}/payments/initiate`,
    {
      campaign_id:  campaignId,
      milestone_id: milestoneId,
      amount,
      is_anonymous: isAnonymous,
      email:        isAnonymous ? email : null,
    },
    { headers: { Authorization: `Bearer ${getAccessToken()}` } }
  );
  return res.data;
  // returns: { order_id, amount, currency, gateway, mock_payment_id, mock_signature, ... }
}

/**
 * Step 2 — Verify payment
 * For mock: pass mock_payment_id and mock_signature directly.
 * For Razorpay: pass razorpay_payment_id and razorpay_signature from SDK callback.
 */
export async function verifyPayment({ orderId, paymentId, signature }) {
  const res = await axios.post(
    `${API_BASE}/payments/verify`,
    {
      order_id:   orderId,
      payment_id: paymentId,
      signature,
    },
    { headers: { Authorization: `Bearer ${getAccessToken()}` } }
  );
  return res.data;
  // returns: { message, transaction_id, amount, campaign, milestone }
}
```

```jsx
// DonateButton.jsx

async function handleDonate() {
  setLoading(true);
  try {
    // Phase 1
    const order = await initiatePayment({
      campaignId:  selectedCampaign.id,
      milestoneId: activeMilestone.id,
      amount,
      isAnonymous,
      email: isAnonymous ? anonymousEmail : null,
    });

    // ── Mock only: no real modal, just verify immediately ──
    // ── Real Razorpay: open SDK modal here, get payment_id + signature from callback ──
    const result = await verifyPayment({
      orderId:   order.order_id,
      paymentId: order.mock_payment_id,    // Razorpay: response.razorpay_payment_id
      signature: order.mock_signature,     // Razorpay: response.razorpay_signature
    });

    setTransactionId(result.transaction_id);
    setSuccess(true);

  } catch (err) {
    setError(err.response?.data?.detail || "Payment failed");
  } finally {
    setLoading(false);
  }
}
```

---

## 8. Testing with curl / Postman

### Step 0 — Login and get token
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"Test@1234","role":"user"}' \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

echo "Token: $TOKEN"
```

### Step 1 — Initiate payment
```bash
curl -s -X POST http://localhost:8000/payments/initiate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "campaign_id":  1,
    "milestone_id": 1,
    "amount":       500,
    "is_anonymous": false
  }' | python3 -m json.tool
```

Save the response values:
```bash
# From the initiate response, set these:
ORDER_ID="MOCK_ORDER_A3F8BC2E91D4"
PAYMENT_ID="MOCK_PAY_9C1D2E3F4A5B"
SIGNATURE="e3b0c44298fc1c149..."
```

### Step 2 — Verify payment
```bash
curl -s -X POST http://localhost:8000/payments/verify \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"order_id\":   \"$ORDER_ID\",
    \"payment_id\": \"$PAYMENT_ID\",
    \"signature\":  \"$SIGNATURE\"
  }" | python3 -m json.tool
```

### Step 3 — Track donation (no auth needed)
```bash
curl -s http://localhost:8000/donations/TXN-B1C2D3E4F5A6 | python3 -m json.tool
```

### Full one-liner test script
```bash
#!/bin/bash
# test_payment.sh — full mock payment flow from CLI

BASE="http://localhost:8000"
EMAIL="user@example.com"
PASS="Test@1234"
CAMPAIGN_ID=1
MILESTONE_ID=1
AMOUNT=500

echo "==> Logging in..."
RESPONSE=$(curl -s -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\",\"role\":\"user\"}")
TOKEN=$(echo $RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "Token obtained."

echo ""
echo "==> Initiating payment..."
INITIATE=$(curl -s -X POST "$BASE/payments/initiate" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"campaign_id\":$CAMPAIGN_ID,\"milestone_id\":$MILESTONE_ID,\"amount\":$AMOUNT,\"is_anonymous\":false}")
echo $INITIATE | python3 -m json.tool

ORDER_ID=$(echo $INITIATE   | python3 -c "import sys,json; print(json.load(sys.stdin)['order_id'])")
PAYMENT_ID=$(echo $INITIATE | python3 -c "import sys,json; print(json.load(sys.stdin)['mock_payment_id'])")
SIGNATURE=$(echo $INITIATE  | python3 -c "import sys,json; print(json.load(sys.stdin)['mock_signature'])")

echo ""
echo "==> Verifying payment..."
VERIFY=$(curl -s -X POST "$BASE/payments/verify" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"order_id\":\"$ORDER_ID\",\"payment_id\":\"$PAYMENT_ID\",\"signature\":\"$SIGNATURE\"}")
echo $VERIFY | python3 -m json.tool

TXN=$(echo $VERIFY | python3 -c "import sys,json; print(json.load(sys.stdin)['transaction_id'])")

echo ""
echo "==> Tracking donation (public)..."
curl -s "$BASE/donations/$TXN" | python3 -m json.tool
```

---

## 9. Error Reference

| HTTP | `detail` | Cause | Fix |
|---|---|---|---|
| 404 | Campaign not found or not active | Campaign doesn't exist or `status != active` | Use an active campaign |
| 404 | Milestone not found for this campaign | Wrong `milestone_id` or wrong `campaign_id` | Verify both IDs |
| 400 | Milestone is 'locked'. Only active milestones accept donations. | Milestone hasn't been unlocked yet | Donate to the currently active milestone |
| 400 | Payment order expired after 15 minutes | > 15 min between initiate and verify | Call initiate again |
| 400 | Payment signature verification failed | `signature` doesn't match | Use the signature from initiate response without modification |
| 400 | Payment ID mismatch | `payment_id` doesn't match stored value | Use the `mock_payment_id` from initiate response |
| 400 | Payment already verified | `verify` called twice on same `order_id` | Each order can only be verified once |
| 400 | Payment order has failed | Order expired or campaign deactivated | Call initiate again |
| 422 | field required / value error | Pydantic validation failed | Check request body types and ranges |
| 429 | Too many requests | Rate limit hit (10 req/min per IP) | Wait and retry |
| 500 | Failed to create payment order. Please retry. | Hash collision on `order_id` (< 1 in 10^14) | Retry |
| 500 | Payment was received but donation recording failed | DB error after signature verified | Contact support with `order_id` |

---

## 10. Migrating to Real Razorpay

When you're ready to accept real payments, only **one file changes**: `app/routes/payments.py`.

### Step 1 — Install SDK
```bash
pip install razorpay
```

### Step 2 — Add keys to .env
```ini
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxx
RAZORPAY_KEY_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
```

### Step 3 — Add to config.py
```python
RAZORPAY_KEY_ID:     str = ""
RAZORPAY_KEY_SECRET: str = ""
```

### Step 4 — Replace these two functions in payments.py

```python
# ── BEFORE (mock) ──────────────────────────────────────────────
def _generate_order_id() -> str:
    return f"MOCK_ORDER_{uuid.uuid4().hex[:12].upper()}"

def _compute_signature(order_id: str, payment_id: str) -> str:
    message = f"{order_id}|{payment_id}".encode()
    key     = settings.JWT_SECRET.encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


# ── AFTER (Razorpay) ───────────────────────────────────────────
import razorpay

_rzp_client = None

def _get_razorpay_client():
    global _rzp_client
    if _rzp_client is None:
        _rzp_client = razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        )
    return _rzp_client

def _generate_order_id(amount: float) -> str:
    """Creates a real Razorpay order and returns its order_id."""
    client = _get_razorpay_client()
    order  = client.order.create({
        "amount":   int(amount * 100),  # Razorpay uses paise (1 INR = 100 paise)
        "currency": "INR",
        "payment_capture": 1,
    })
    return order["id"]  # e.g. "order_AbCdEfGhIjKlMn"

def _compute_signature(order_id: str, payment_id: str) -> str:
    """Razorpay signature — same HMAC formula, different key."""
    message = f"{order_id}|{payment_id}".encode()
    key     = settings.RAZORPAY_KEY_SECRET.encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()
```

### Step 5 — Update initiate endpoint

In `initiate_payment()`, change the order creation block:

```python
# BEFORE
order_id   = _generate_order_id()
payment_id = _generate_payment_id()
signature  = _compute_signature(order_id, payment_id)

# AFTER
order_id   = _generate_order_id(payload.amount)  # calls Razorpay API
payment_id = None   # Razorpay SDK returns this after user completes payment
signature  = None   # Razorpay SDK returns this via onSuccess callback
```

Remove `mock_payment_id` and `mock_signature` from the response — the frontend Razorpay SDK now handles these via its own callback.

### Step 6 — Update frontend

Add the Razorpay JS SDK to your HTML:
```html
<script src="https://checkout.razorpay.com/v1/checkout.js"></script>
```

Then open the payment modal:
```javascript
const order = await initiatePayment({ ... });  // same API call

const options = {
  key:         "rzp_test_xxxxxxxxxxxx",   // RAZORPAY_KEY_ID
  amount:      order.amount * 100,        // paise
  currency:    "INR",
  order_id:    order.order_id,
  description: order.description,
  handler: async (response) => {
    // Razorpay calls this on success — field names match our verify endpoint
    const result = await verifyPayment({
      orderId:   response.razorpay_order_id,
      paymentId: response.razorpay_payment_id,
      signature: response.razorpay_signature,
    });
    console.log("Donation confirmed:", result.transaction_id);
  },
};

const rzp = new window.Razorpay(options);
rzp.open();
```

The backend `/payments/verify` requires **zero changes**.

---

## 11. Migrating to Stripe

### Key differences from Razorpay

| | Razorpay | Stripe |
|---|---|---|
| Order creation | `razorpay.order.create()` | `stripe.PaymentIntent.create()` |
| Frontend modal | Razorpay Checkout JS | Stripe Elements / Payment Sheet |
| Signature verification | HMAC on `order_id\|payment_id` | Webhook `stripe.Webhook.construct_event()` |
| Confirm method | Two-phase (order → payment) | Single PaymentIntent |

For Stripe, the `/payments/verify` endpoint would accept a `payment_intent_id` instead of `order_id + signature`, and verification would happen via webhook. The `PaymentOrder` model and the donation-creation logic remain the same.

---

## 12. Security Notes

| Topic | Implementation |
|---|---|
| Signature verification | `hmac.compare_digest()` — constant-time, prevents timing attacks |
| Anonymous email storage | Fernet AES-128-CBC encrypted, never stored plain-text |
| Order expiry | 15-minute window; expired orders auto-marked `failed` |
| Order ownership | Non-anonymous order status check enforces `user_id` match |
| Race condition on `raised_amount` | Atomic SQL `UPDATE … SET raised_amount = raised_amount + ?` |
| Idempotency | Verifying the same `order_id` twice returns 400 "already verified" |
| Rate limiting | 10 req/min per IP on both initiate and verify |
| Max donation amount | ₹10,00,000 enforced at Pydantic layer before any DB write |

---

## 13. File Map

```
app/
├── models/
│   └── payment_order.py          ← PaymentOrder SQLAlchemy model
├── routes/
│   └── payments.py               ← 3 endpoints: initiate, verify, order-status
├── helper/
│   └── pydantic_helper.py        ← PaymentInitiateRequest/Response,
│                                    PaymentVerifyRequest/Response schemas
└── main.py                       ← payments router registered here

alembic/versions/
└── a1b2c3d4e5f6_add_payment_orders_table.py   ← DB migration
```

### Quick reference — what to edit per gateway swap

| File | Mock → Razorpay | Mock → Stripe |
|---|---|---|
| `app/routes/payments.py` | Replace `_generate_order_id()` and `_compute_signature()` | Replace verification logic in `verify_payment()` |
| `app/core/config.py` | Add `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` | Add `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` |
| `app/helper/pydantic_helper.py` | Remove `mock_payment_id`, `mock_signature` from response schema | Change verify request schema to `payment_intent_id` |
| Frontend JS | Swap `mock_payment_id/signature` for Razorpay SDK callback fields | Use Stripe Elements |
| `app/models/payment_order.py` | No changes | No changes |
| `alembic/versions/…` | No changes | No changes |
