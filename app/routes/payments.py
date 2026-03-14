"""
payments.py — Mock Payment Gateway

Two-phase commit pattern:
  1. POST /payments/initiate  →  create PaymentOrder (status=pending), return order_id
  2. POST /payments/verify    →  verify signature, create Donation atomically, mark order paid

Why two phases?
  - Donation row is only written after payment is confirmed — no phantom/unverified donations.
  - Signature verification is structurally identical to real Razorpay, so swapping gateways
    requires changing only _compute_signature() and _create_gateway_order().

Mock signature scheme:
  HMAC-SHA256(f"{order_id}|{payment_id}", key=settings.JWT_SECRET)
  — This is exactly how Razorpay computes razorpay_signature, just with a different key name.
"""
import hashlib
import hmac
import uuid
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, get_db
from app.models.campaign import Campaign
from app.models.donation import Donation
from app.models.email_notification import EmailNotification
from app.models.milestone import Milestone
from app.models.payment_order import PaymentOrder
from app.utils.email_crypto import encrypt_email
from app.utils.email_service import send_email
from app.helper.pydantic_helper import (
    PaymentInitiateRequest,
    PaymentInitiateResponse,
    PaymentVerifyRequest,
    PaymentVerifyResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["Payments"])

# ── Constants ────────────────────────────────────────────────────────────────
ORDER_EXPIRY_MINUTES = 15   # payment window; expired orders cannot be verified
GATEWAY              = "mock"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    """Timezone-naive UTC — consistent with all other DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _generate_order_id() -> str:
    """MOCK_ORDER_<12 hex chars>  →  e.g. MOCK_ORDER_A3F8BC2E91D4"""
    return f"MOCK_ORDER_{uuid.uuid4().hex[:12].upper()}"


def _generate_payment_id() -> str:
    """MOCK_PAY_<12 hex chars>  →  e.g. MOCK_PAY_9C1D2E3F4A5B"""
    return f"MOCK_PAY_{uuid.uuid4().hex[:12].upper()}"


def _compute_signature(order_id: str, payment_id: str) -> str:
    """
    HMAC-SHA256(f"{order_id}|{payment_id}", key=JWT_SECRET).

    Razorpay equivalent:
        hmac.new(
            api_secret.encode(),
            f"{razorpay_order_id}|{razorpay_payment_id}".encode(),
            hashlib.sha256
        ).hexdigest()

    Swap the key source and you get real Razorpay verification.
    """
    message = f"{order_id}|{payment_id}".encode()
    key     = settings.JWT_SECRET.encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def _verify_signature(order_id: str, payment_id: str, provided_signature: str) -> bool:
    expected = _compute_signature(order_id, payment_id)
    # Use hmac.compare_digest to prevent timing attacks
    return hmac.compare_digest(expected, provided_signature)


# ── 1. POST /payments/initiate ───────────────────────────────────────────────

@router.post(
    "/initiate",
    response_model=PaymentInitiateResponse,
    dependencies=[Depends(rate_limit("payment:initiate", limit=10, window_seconds=60))],
)
def initiate_payment(
    payload:      PaymentInitiateRequest,
    current_user = Depends(get_current_user),
    db: Session  = Depends(get_db),
):
    """
    Step 1 of 2 — Creates a pending PaymentOrder.

    Frontend flow:
        POST /payments/initiate  →  receive { order_id, mock_payment_id, mock_signature }
        Show "payment modal" (mock: auto-fill from response)
        POST /payments/verify    →  send back the three values above
    """
    # ── Validate campaign ────────────────────────────────────────────────────
    campaign = db.query(Campaign).filter(
        Campaign.id     == payload.campaign_id,
        Campaign.status == "active",
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found or not active")

    # ── Validate milestone ───────────────────────────────────────────────────
    milestone = db.query(Milestone).filter(
        Milestone.id          == payload.milestone_id,
        Milestone.campaign_id == payload.campaign_id,
    ).first()
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found for this campaign")

    if milestone.status not in ("active",):
        raise HTTPException(
            status_code=400,
            detail=f"Milestone is '{milestone.status}'. Only active milestones accept donations.",
        )

    # ── Encrypt anonymous email if provided ─────────────────────────────────
    encrypted_email = None
    if payload.is_anonymous and payload.email:
        try:
            encrypted_email = encrypt_email(payload.email)
        except Exception as exc:
            logger.error("Email encryption failed: %s", exc)
            raise HTTPException(status_code=500, detail="Failed to process anonymous donor data")

    # ── Create gateway order ─────────────────────────────────────────────────
    order_id   = _generate_order_id()
    payment_id = _generate_payment_id()              # mock: pre-generated
    signature  = _compute_signature(order_id, payment_id)  # mock: pre-computed

    order = PaymentOrder(
        user_id         = None if payload.is_anonymous else current_user.id,
        campaign_id     = payload.campaign_id,
        milestone_id    = payload.milestone_id,
        amount          = payload.amount,
        is_anonymous    = payload.is_anonymous,
        anonymous_email = encrypted_email,
        order_id        = order_id,
        payment_id      = payment_id,   # stored so verify can cross-check
        gateway         = GATEWAY,
        status          = "pending",
        expires_at      = _utcnow() + timedelta(minutes=ORDER_EXPIRY_MINUTES),
    )

    try:
        db.add(order)
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.error("Duplicate order_id collision — extremely unlikely: %s", order_id)
        raise HTTPException(status_code=500, detail="Failed to create payment order. Please retry.")

    logger.info(
        "Payment order created: order_id=%s user_id=%s amount=%.2f",
        order_id, order.user_id, payload.amount,
    )

    return PaymentInitiateResponse(
        order_id        = order_id,
        amount          = payload.amount,
        gateway         = GATEWAY,
        description     = f"Donation to '{campaign.title}' — {milestone.title}",
        # ── Mock-only extra fields ──────────────────────────────────────────
        # In prod these would NOT be set; Razorpay SDK handles them.
        # Included so frontend can call /verify without a real modal.
        mock_payment_id = payment_id,
        mock_signature  = signature,
    )


# ── 2. POST /payments/verify ─────────────────────────────────────────────────

@router.post(
    "/verify",
    response_model=PaymentVerifyResponse,
    dependencies=[Depends(rate_limit("payment:verify", limit=10, window_seconds=60))],
)
def verify_payment(
    payload:      PaymentVerifyRequest,
    current_user = Depends(get_current_user),
    db: Session  = Depends(get_db),
):
    """
    Step 2 of 2 — Verify payment signature and create Donation.

    On success:
      - PaymentOrder.status  →  "paid"
      - Donation row created
      - Campaign.raised_amount atomically incremented
      - Confirmation email sent (anonymous donors only)
    """
    # ── Fetch order ──────────────────────────────────────────────────────────
    order = (
        db.query(PaymentOrder)
        .filter(PaymentOrder.order_id == payload.order_id)
        .first()
    )

    if not order:
        raise HTTPException(status_code=404, detail="Payment order not found")

    if order.status == "paid":
        raise HTTPException(status_code=400, detail="Payment already verified")

    if order.status == "failed":
        raise HTTPException(status_code=400, detail="Payment order has failed. Please initiate a new payment.")

    # ── Expiry check ─────────────────────────────────────────────────────────
    if order.expires_at < _utcnow():
        order.status = "failed"
        db.commit()
        raise HTTPException(
            status_code=400,
            detail=f"Payment order expired after {ORDER_EXPIRY_MINUTES} minutes. Please initiate a new payment.",
        )

    # ── Signature verification (timing-safe) ─────────────────────────────────
    if not _verify_signature(payload.order_id, payload.payment_id, payload.signature):
        logger.warning(
            "Signature mismatch for order_id=%s — possible tamper attempt", payload.order_id
        )
        raise HTTPException(status_code=400, detail="Payment signature verification failed")

    # ── Cross-check stored payment_id ────────────────────────────────────────
    # (mock only: in real Razorpay the payment_id is returned by the SDK so
    #  checking against a stored value is not needed — remove this block
    #  when integrating real Razorpay)
    if order.payment_id and order.payment_id != payload.payment_id:
        raise HTTPException(status_code=400, detail="Payment ID mismatch")

    # ── Re-validate campaign & milestone are still active ────────────────────
    campaign = db.query(Campaign).filter(
        Campaign.id     == order.campaign_id,
        Campaign.status == "active",
    ).first()
    if not campaign:
        order.status = "failed"
        db.commit()
        raise HTTPException(status_code=400, detail="Campaign is no longer active")

    milestone = db.query(Milestone).filter(
        Milestone.id == order.milestone_id,
    ).first()
    if not milestone:
        order.status = "failed"
        db.commit()
        raise HTTPException(status_code=400, detail="Milestone not found")

    # ── Create Donation (the only authoritative record of money received) ────
    transaction_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"

    donation = Donation(
        campaign_id    = order.campaign_id,
        milestone_id   = order.milestone_id,
        amount         = order.amount,
        is_anonymous   = order.is_anonymous,
        user_id        = order.user_id,
        transaction_id = transaction_id,
    )

    try:
        db.add(donation)
        db.flush()  # get donation.id without committing yet

        # ── Atomic raised_amount increment (fixes read-modify-write race) ───
        db.execute(
            sa_update(Campaign)
            .where(Campaign.id == order.campaign_id)
            .values(raised_amount=Campaign.raised_amount + order.amount)
        )

        # ── Mark order as paid and link to donation ─────────────────────────
        order.status      = "paid"
        order.payment_id  = payload.payment_id
        order.donation_id = donation.id

        db.commit()
        db.refresh(donation)

    except Exception as exc:
        db.rollback()
        logger.error("Failed to finalize donation for order_id=%s: %s", payload.order_id, exc)
        raise HTTPException(status_code=500, detail="Payment was received but donation recording failed. Contact support with order_id.")

    logger.info(
        "Donation created: txn=%s order=%s amount=%.2f campaign_id=%s",
        transaction_id, payload.order_id, order.amount, order.campaign_id,
    )

    # ── Anonymous donor email notification ───────────────────────────────────
    if order.is_anonymous and order.anonymous_email:
        try:
            from app.utils.email_crypto import decrypt_email
            plain_email = decrypt_email(order.anonymous_email)
            tracker_url = f"{settings.FRONTEND_URL}/track?txn={transaction_id}"
            send_email(
                plain_email,
                subject=f"Donation Received — ₹{order.amount:.0f} to {campaign.title}",
                body=f"""Thank you for your donation!

Amount    : ₹{order.amount:.2f}
Campaign  : {campaign.title}
Milestone : {milestone.title}

Your Transaction ID : {transaction_id}

Track your donation anytime (no login needed):
{tracker_url}

You will receive another email once the NGO
uploads proof that your donation was used.

Your identity has NOT been stored on our platform.
""",
            )

            # Persist EmailNotification for proof-upload alerts
            from datetime import timedelta as td
            notify = EmailNotification(
                donation_id     = donation.id,
                encrypted_email = order.anonymous_email,
                expires_at      = _utcnow() + td(days=30),
            )
            db.add(notify)
            db.commit()

        except Exception as exc:
            # Non-fatal — donation is already confirmed
            logger.error(
                "Failed to send confirmation email for txn=%s: %s", transaction_id, exc
            )

    return PaymentVerifyResponse(
        message        = "Payment successful. Donation recorded.",
        transaction_id = transaction_id,
        amount         = order.amount,
        campaign       = campaign.title,
        milestone      = milestone.title,
    )


# ── 3. GET /payments/order/{order_id} ── Status check ────────────────────────

@router.get("/order/{order_id}")
def get_order_status(
    order_id:    str,
    current_user = Depends(get_current_user),
    db: Session  = Depends(get_db),
):
    """
    Frontend can poll this to check if an order is still pending / already paid.
    Only the user who created the order can query it (or if anonymous, any authenticated user).
    """
    order = db.query(PaymentOrder).filter(PaymentOrder.order_id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # For non-anonymous orders, enforce ownership
    if not order.is_anonymous and order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    is_expired = (order.status == "pending" and order.expires_at < _utcnow())

    return {
        "order_id":   order.order_id,
        "status":     "expired" if is_expired else order.status,
        "amount":     order.amount,
        "gateway":    order.gateway,
        "expires_at": order.expires_at,
        # Only expose transaction_id if paid
        "transaction_id": (
            db.query(Donation.transaction_id)
              .filter(Donation.id == order.donation_id)
              .scalar()
            if order.donation_id else None
        ),
    }
