import math
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import func, distinct
from sqlalchemy.orm import Session, joinedload

from app.core.security import get_current_user, verify_password, hash_password
from app.core.rate_limit import rate_limit
from app.db.session import SessionLocal
from app.core.security import get_db
from app.models.user import User
from app.models.donation import Donation
from app.models.refresh_token import RefreshToken
from app.helper.pydantic_helper import (
    UserProfileResponse,
    UserUpdateRequest,
    PasswordChangeRequest,
    DonationStatsResponse,
    DonationOut,
    CampaignMini,
    PaginatedDonationsResponse,
)

router = APIRouter(prefix="/users", tags=["User Dashboard"])


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _revoke_all_tokens(user_id: int):
    """Background task — creates its own DB session (request session is already closed)."""
    db = SessionLocal()
    try:
        now = _utcnow()
        db.query(RefreshToken).filter(
            RefreshToken.user_id   == user_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        ).update({"revoked_at": now}, synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ── 1. GET /users/me ──────────────────────────────────────
@router.get("/me", response_model=UserProfileResponse)
def get_my_profile(
    current_user: User = Depends(get_current_user),
):
    return current_user


# ── 2. PUT /users/me ──────────────────────────────────────
@router.put("/me", response_model=UserProfileResponse)
def update_my_profile(
    payload:      UserUpdateRequest,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    if payload.full_name is None and payload.phone is None:
        raise HTTPException(
            status_code=422,
            detail="Provide at least one field to update: full_name or phone",
        )
    if payload.full_name is not None:
        current_user.full_name = payload.full_name
    if payload.phone is not None:
        current_user.phone = payload.phone
    try:
        db.commit()
        db.refresh(current_user)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update profile")
    return current_user


# ── 3. PUT /users/me/password ─────────────────────────────
@router.put("/me/password")
def change_my_password(
    payload:          PasswordChangeRequest,
    background_tasks: BackgroundTasks,
    current_user:     User    = Depends(get_current_user),
    db:               Session = Depends(get_db),
    _rl = Depends(rate_limit("user:password_change", limit=5, window_seconds=300)),
):
    if not verify_password(payload.current_password, current_user.password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if verify_password(payload.new_password, current_user.password):
        raise HTTPException(
            status_code=400,
            detail="New password must be different from the current password",
        )

    current_user.password              = hash_password(payload.new_password)
    current_user.failed_login_attempts = 0
    current_user.locked_until          = None

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update password")

    background_tasks.add_task(_revoke_all_tokens, current_user.id)

    return {"message": "Password changed successfully. All other sessions have been logged out."}


# ── 4. GET /users/me/stats ────────────────────────────────
@router.get("/me/stats", response_model=DonationStatsResponse)
def get_my_stats(
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    now         = _utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    row = (
        db.query(
            func.coalesce(func.sum(Donation.amount),          0.0).label("total_donated"),
            func.count(Donation.id)                              .label("total_donations"),
            func.count(distinct(Donation.campaign_id))           .label("campaigns_supported"),
            func.min(Donation.created_at)                        .label("first_donation_date"),
        )
        .filter(Donation.user_id == current_user.id)
        .one()
    )

    this_month = (
        db.query(func.coalesce(func.sum(Donation.amount), 0.0))
        .filter(
            Donation.user_id    == current_user.id,
            Donation.created_at >= month_start,
        )
        .scalar()
    ) or 0.0

    return DonationStatsResponse(
        total_donated       = float(row.total_donated),
        total_donations     = int(row.total_donations),
        campaigns_supported = int(row.campaigns_supported),
        this_month_donated  = float(this_month),
        first_donation_date = row.first_donation_date.date()
                              if row.first_donation_date else None,
    )


# ── 5. GET /users/me/donations ────────────────────────────
@router.get("/me/donations", response_model=PaginatedDonationsResponse)
def get_my_donations(
    page:         int           = 1,
    limit:        int           = 10,
    campaign_id:  Optional[int] = None,
    sort_order:   str           = "desc",
    current_user: User          = Depends(get_current_user),
    db:           Session       = Depends(get_db),
):
    limit = max(1, min(limit, 50))
    page  = max(1, page)

    if sort_order not in ("asc", "desc"):
        raise HTTPException(status_code=422, detail="sort_order must be 'asc' or 'desc'")

    base_q = (
        db.query(Donation)
        .options(joinedload(Donation.campaign))
        .filter(Donation.user_id == current_user.id)
    )
    if campaign_id is not None:
        base_q = base_q.filter(Donation.campaign_id == campaign_id)

    total_count = base_q.count()
    order_col   = (Donation.created_at.asc()
                   if sort_order == "asc" else Donation.created_at.desc())
    donations   = (base_q.order_by(order_col)
                         .offset((page - 1) * limit)
                         .limit(limit)
                         .all())
    total_pages = math.ceil(total_count / limit) if total_count > 0 else 1

    return PaginatedDonationsResponse(
        data=[
            DonationOut(
                id             = d.id,
                transaction_id = d.transaction_id,
                amount         = d.amount,
                is_anonymous   = d.is_anonymous,
                campaign_id    = d.campaign_id,
                campaign       = CampaignMini(id=d.campaign.id, title=d.campaign.title)
                                 if d.campaign else None,
                created_at     = d.created_at,
            )
            for d in donations
        ],
        total_count = total_count,
        page        = page,
        limit       = limit,
        total_pages = total_pages,
        has_more    = (page * limit) < total_count,
    )


# ── 6. GET /users/me/donations/{id} ──────────────────────
@router.get("/me/donations/{donation_id}", response_model=DonationOut)
def get_my_donation(
    donation_id:  int,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    donation = (
        db.query(Donation)
        .options(joinedload(Donation.campaign))
        .filter(
            Donation.id      == donation_id,
            Donation.user_id == current_user.id,   # ownership enforced here
        )
        .first()
    )
    if not donation:
        raise HTTPException(status_code=404, detail="Donation not found")

    return DonationOut(
        id             = donation.id,
        transaction_id = donation.transaction_id,
        amount         = donation.amount,
        is_anonymous   = donation.is_anonymous,
        campaign_id    = donation.campaign_id,
        campaign       = CampaignMini(id=donation.campaign.id, title=donation.campaign.title)
                         if donation.campaign else None,
        created_at     = donation.created_at,
    )
