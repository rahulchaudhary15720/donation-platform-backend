from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.roles import admin_required
from app.core.security import get_db
from app.models.user import User
# from app.models.ngo import NGO
from app.models.ngo import NGO
from app.models.proof import Proof
from app.models.milestone import Milestone
from app.models.campaign import Campaign
from app.models.email_notification import EmailNotification
from app.utils.email_crypto import decrypt_email
from app.utils.email_service import send_email
from app.core.roles import ngo_required
from app.utils.email_verification_service import (
    generate_verification_token, send_verification_email, send_welcome_email,send_deactivation_email
    
)

router = APIRouter(prefix="/admin", tags=["Admin"])

@router.get("/ngos/pending")
def pending_ngos(db: Session = Depends(get_db), _=Depends(admin_required)):
    return db.query(User).filter(User.role == "ngo", User.is_active == False).all()
    # return (
    #     db.query(NGO)
    #     .join(User, NGO.email == User.email)
    #     .filter(User.role == "ngo", User.is_active == False)
    #     .all()
    # )

@router.post("/ngos/{ngo_id}/approve")
def approve_ngo(ngo_id: int, db: Session = Depends(get_db), _=Depends(admin_required)):
    # ngo = db.query(NGO).get(ngo_id)
    # if not ngo:
    #     raise HTTPException(404, "NGO not found")
    #
    # user = db.query(User).filter(User.email == ngo.email).first()
    # if not user:
    #     raise HTTPException(404, "User not found for NGO")
    #
    # user.is_active = True

    user = db.query(User).get(ngo_id)
    if not user or user.role != "ngo":
        raise HTTPException(404, "NGO not found")

    user.is_active = True

    db.commit()
    # Send welcome email now
    try:
        send_welcome_email(user.email, user.role)
    except Exception as e:
        print(f"Failed to send welcome email to NGO: {e}")

    return {"message": "NGO approved and activated"}

@router.post("/ngos/{ngo_id}/disapprove")
def disapprove_ngo(ngo_id: int, db: Session = Depends(get_db), _=Depends(admin_required)):
    # ngo = db.query(NGO).get(ngo_id)
    # if not ngo:
    #     raise HTTPException(404, "NGO not found")
    #
    # user = db.query(User).filter(User.email == ngo.email).first()
    # if not user:
    #     raise HTTPException(404, "User not found for NGO")
    #
    # user.is_active = True

    user = db.query(User).get(ngo_id)
    if not user or user.role != "ngo":
        raise HTTPException(404, "NGO not found")

    user.is_active = False

    db.commit()
    # Send welcome email now
    try:
        send_deactivation_email(user.email, user.role)
    except Exception as e:
        print(f"Failed to send welcome email to NGO: {e}")

    return {"message": "NGO dapproved and deactivated"}


@router.post("/proofs/{proof_id}/verify")
def verify_proof(proof_id: int, db: Session = Depends(get_db), _=Depends(admin_required)):
    proof = db.query(Proof).get(proof_id)
    proof.verified = True
    db.commit()

    notify = db.query(EmailNotification)\
        .filter(EmailNotification.donation_id == proof.milestone_id)\
        .first()

    if notify:
        email = decrypt_email(notify.encrypted_email)
        send_email(email, "Donation Used", "NGO proof verified.")
        db.delete(notify)
        db.commit()

    return {"message": "Proof verified"}


@router.patch("/{campaign_id}/activate")
def activate_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    count = db.query(Milestone)\
        .filter(Milestone.campaign_id == campaign_id)\
        .count()

    if count < 3:
        raise HTTPException(400, "Minimum 3 milestones required")

    campaign = db.query(Campaign).get(campaign_id)
    campaign.status = "active"

    db.commit()
    return {"message": "Campaign activated"}



# -------------------------------
# Approve a proof
# -------------------------------
@router.post("/{proof_id}/approve")
def approve_proof(
    proof_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    proof = db.query(Proof).get(proof_id)
    if not proof:
        raise HTTPException(404, "Proof not found")

    milestone = proof.milestone
    campaign = db.query(Campaign).get(milestone.campaign_id)
    ngo = db.query(NGO).filter(NGO.user_id == current_user.id).first()

    # Ownership check
    if campaign.ngo_id != ngo.id:
        raise HTTPException(403, "Not allowed")

    # Approve the proof
    proof.verified = True
    milestone.status = "completed"
    db.commit()

    # Activate the next milestone
    next_milestone = (
        db.query(Milestone)
        .filter(
            Milestone.campaign_id == campaign.id,
            Milestone.order_number == milestone.order_number + 1
        )
        .first()
    )

    if next_milestone:
        next_milestone.status = "active"
        db.commit()

    return {"message": "Proof approved and next milestone activated"}
