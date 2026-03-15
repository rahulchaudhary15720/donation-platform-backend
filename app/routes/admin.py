from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.roles import admin_required
from app.core.security import get_db
from app.models.user import User
# from app.models.ngo import NGO
from app.models.ngo import NGO
from app.models.proof import Proof
from app.models.milestone import Milestone
from app.models.campaign import Campaign
from app.models.donation import Donation
from app.models.refresh_token import RefreshToken
from app.models.email_notification import EmailNotification
from app.utils.email_crypto import decrypt_email
from app.utils.email_service import send_email
from app.core.roles import ngo_required
from app.utils.email_verification_service import (
    generate_verification_token, send_verification_email, send_welcome_email,send_deactivation_email
    
)

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/overview")
def admin_overview(db: Session = Depends(get_db), _=Depends(admin_required)):
    total_users = db.query(func.count(User.id)).scalar() or 0
    total_ngos = db.query(func.count(User.id)).filter(User.role == "ngo").scalar() or 0
    pending_ngos = (
        db.query(func.count(User.id))
        .filter(User.role == "ngo", User.is_active.is_(False))
        .scalar()
        or 0
    )
    active_campaigns = (
        db.query(func.count(Campaign.id))
        .filter(Campaign.status == "active")
        .scalar()
        or 0
    )
    pending_proofs = (
        db.query(func.count(Proof.id))
        .filter(Proof.verified.is_(False))
        .scalar()
        or 0
    )
    total_raised = db.query(func.coalesce(func.sum(Donation.amount), 0.0)).scalar() or 0.0

    return {
        "total_users": int(total_users),
        "total_ngos": int(total_ngos),
        "pending_ngos": int(pending_ngos),
        "active_campaigns": int(active_campaigns),
        "pending_proofs": int(pending_proofs),
        "total_raised": float(total_raised),
    }


@router.get("/users")
def admin_users(
    role: str | None = None,
    is_active: bool | None = None,
    q: str | None = None,
    page: int = 1,
    limit: int = 20,
    db: Session = Depends(get_db),
    _=Depends(admin_required),
):
    page = max(1, page)
    limit = max(1, min(limit, 100))

    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    if is_active is not None:
        query = query.filter(User.is_active.is_(is_active))
    if q:
        search = f"%{q.strip()}%"
        query = query.filter(
            User.email.ilike(search)
            | User.full_name.ilike(search)
            | User.phone.ilike(search)
        )

    total_count = query.count()
    users = (
        query.order_by(User.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    return {
        "data": [
            {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "phone": user.phone,
                "role": user.role,
                "is_active": user.is_active,
                "email_verified": user.email_verified,
                "last_login_at": user.last_login_at.isoformat() if user.last_login_at else "",
                "created_at": user.created_at.isoformat() if user.created_at else "",
            }
            for user in users
        ],
        "total_count": total_count,
        "page": page,
        "limit": limit,
        "total_pages": (total_count + limit - 1) // limit,
    }


@router.patch("/users/{user_id}/deactivate")
def admin_deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    if current_user.id == user_id:
        raise HTTPException(400, "You cannot deactivate your own admin account")

    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(404, "User not found")

    if not user.is_active:
        return {"message": "User is already deactivated"}

    user.is_active = False
    db.query(RefreshToken).filter(RefreshToken.user_id == user_id).update(
        {"revoked_at": func.now()}, synchronize_session=False
    )
    db.commit()

    return {"message": "User deactivated successfully"}


@router.patch("/users/{user_id}/activate")
def admin_activate_user(
    user_id: int,
    db: Session = Depends(get_db),
    _=Depends(admin_required),
):
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(404, "User not found")

    if user.is_active:
        return {"message": "User is already active"}

    user.is_active = True
    db.commit()

    return {"message": "User activated successfully"}


@router.get("/proofs/pending")
def pending_proofs(db: Session = Depends(get_db), _=Depends(admin_required)):
    rows = (
        db.query(Proof, Milestone, Campaign, NGO)
        .join(Milestone, Proof.milestone_id == Milestone.id)
        .join(Campaign, Milestone.campaign_id == Campaign.id)
        .join(NGO, Campaign.ngo_id == NGO.id)
        .filter(Proof.verified.is_(False))
        .order_by(Proof.id.desc())
        .all()
    )

    return [
        {
            "id": proof.id,
            "milestone_id": milestone.id,
            "campaign_id": campaign.id,
            "campaign_title": campaign.title,
            "milestone_title": milestone.title,
            "ngo_name": ngo.name,
            "file_url": proof.file_url,
            "is_verified": proof.verified,
            "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
        }
        for proof, milestone, campaign, ngo in rows
    ]

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
    if not proof:
        raise HTTPException(404, "Proof not found")

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


@router.patch("/campaigns/{campaign_id}/activate")
def admin_activate_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    campaign = db.query(Campaign).get(campaign_id)
    if not campaign:
        raise HTTPException(404, "Campaign not found")

    campaign.status = "active"
    db.commit()

    return {"message": "Campaign activated"}


@router.patch("/campaigns/{campaign_id}/deactivate")
def admin_deactivate_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    campaign = db.query(Campaign).get(campaign_id)
    if not campaign:
        raise HTTPException(404, "Campaign not found")

    campaign.status = "inactive"
    db.commit()

    return {"message": "Campaign deactivated"}


@router.patch("/{campaign_id}/deactivate")
def deactivate_campaign_legacy(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    campaign = db.query(Campaign).get(campaign_id)
    if not campaign:
        raise HTTPException(404, "Campaign not found")

    campaign.status = "inactive"
    db.commit()

    return {"message": "Campaign deactivated"}


@router.patch("/milestones/{milestone_id}/activate")
def admin_activate_milestone(
    milestone_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    milestone = db.query(Milestone).get(milestone_id)
    if not milestone:
        raise HTTPException(404, "Milestone not found")

    milestone.status = "active"
    db.commit()

    return {"message": "Milestone activated"}


@router.patch("/milestones/{milestone_id}/deactivate")
def admin_deactivate_milestone(
    milestone_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    milestone = db.query(Milestone).get(milestone_id)
    if not milestone:
        raise HTTPException(404, "Milestone not found")

    milestone.status = "locked"
    db.commit()

    return {"message": "Milestone deactivated"}



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
    if not campaign:
        raise HTTPException(404, "Campaign not found")

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
