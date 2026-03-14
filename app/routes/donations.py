import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, timedelta

from app.core.security import get_db, get_current_user
from app.core.config import settings
from app.models.donation import Donation
from app.models.campaign import Campaign
from app.models.milestone import Milestone
from app.models.email_notification import EmailNotification
from app.utils.email_crypto import encrypt_email
from app.utils.email_service import send_email

router = APIRouter(prefix="/donations", tags=["Donations"])


# ── 1. POST /donations/ ── Make a donation ────────────────
@router.post("/")
def donate(
    campaign_id:  int,
    milestone_id: int,                    # ← FIXED: was missing before
    amount:       float,
    anonymous:    bool,
    email:        str | None = None,
    user         = Depends(get_current_user),
    db: Session  = Depends(get_db),
):
    # Validate campaign exists and is active
    campaign = db.query(Campaign).filter(
        Campaign.id     == campaign_id,
        Campaign.status == "active"
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found or not active")

    # Validate milestone belongs to this campaign
    milestone = db.query(Milestone).filter(
        Milestone.id          == milestone_id,
        Milestone.campaign_id == campaign_id,
    ).first()
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found for this campaign")

    # Validate amount
    if amount <= 0:
        raise HTTPException(status_code=422, detail="Donation amount must be greater than 0")

    # Generate clean unique transaction ID
    transaction_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"  # e.g. TXN-A3F8BC2E91D4

    # Create donation record
    donation = Donation(
        campaign_id    = campaign_id,
        milestone_id   = milestone_id,
        amount         = amount,
        is_anonymous   = anonymous,
        user_id        = None if anonymous else user.id,
        transaction_id = transaction_id,
    )
    db.add(donation)
    db.commit()
    db.refresh(donation)

    # Update campaign raised_amount
    campaign.raised_amount = (campaign.raised_amount or 0) + amount
    db.commit()

    # Handle anonymous donor email
    if anonymous and email:
        # Encrypt and store email — never stored in plain text
        enc = encrypt_email(email)
        notify = EmailNotification(
            donation_id    = donation.id,
            encrypted_email= enc,
            expires_at     = datetime.utcnow() + timedelta(days=30),
        )
        db.add(notify)
        db.commit()

        # Send proper confirmation email with tracker link
        tracker_url = f"{settings.FRONTEND_URL}/track?txn={transaction_id}"
        send_email(
            email,
            subject=f"Donation Received — ₹{amount:.0f} to {campaign.title}",
            body=f"""Thank you for your donation!

Amount    : ₹{amount:.2f}
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

    return {
        "message":        "Donation successful",
        "transaction_id": transaction_id,
        "campaign":       campaign.title,
        "milestone":      milestone.title,
        "amount":         amount,
    }


# ── 2. GET /donations/{transaction_id} ── Public tracker ──
@router.get("/{transaction_id}")
def track_donation(
    transaction_id: str,
    db: Session = Depends(get_db),
):
    """
    Public endpoint — no login required.
    Anonymous donor visits: /track?txn=TXN-A3F8BC2E91D4
    Frontend calls this endpoint to show donation status.
    Zero PII returned — no user_id, no email.
    """
    donation = (
        db.query(Donation)
        .options(
            joinedload(Donation.campaign),
            joinedload(Donation.milestone),
        )
        .filter(Donation.transaction_id == transaction_id)
        .first()
    )

    if not donation:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return {
        "transaction_id":   donation.transaction_id,
        "amount":           donation.amount,
        "donated_at":       donation.created_at,
        "campaign_title":   donation.campaign.title    if donation.campaign   else None,
        "milestone_title":  donation.milestone.title   if donation.milestone  else None,
        "milestone_status": donation.milestone.status  if donation.milestone  else None,
        # ↑ "locked" / "active" / "completed" — donor can track progress
        # NO user_id, NO email — zero PII ever exposed
    }
