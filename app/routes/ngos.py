from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.security import get_db
from app.core.roles import ngo_required
from app.models.user import User
from app.models.ngo import NGO
from app.models.campaign import Campaign
from app.models.milestone import Milestone
from app.core.security import hash_password
from pydantic import BaseModel, Field, field_validator

router = APIRouter(prefix="/ngos", tags=["NGO"])

class NGOProfileCreate(BaseModel):
    name: str
    description: str
    registration_number: str
    address: str
    phone: str
    website: str

class NGOProfileUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    registration_number: str | None = None
    address: str | None = None
    phone: str | None = None
    website: str | None = None


def _serialize_milestone(m: Milestone) -> dict:
    return {
        "id": m.id,
        "title": m.title,
        "description": m.description,
        "target_amount": m.target_amount,
        "order_number": m.order_number,
        "status": m.status,
    }


def _serialize_campaign(campaign: Campaign, milestones: list[Milestone]) -> dict:
    return {
        "id": campaign.id,
        "ngo_id": campaign.ngo_id,
        "title": campaign.title,
        "description": campaign.description,
        "purpose": campaign.purpose,
        "image_url": campaign.image_url,
        "target_amount": campaign.target_amount,
        "raised_amount": campaign.raised_amount,
        "status": campaign.status,
        "created_at": campaign.created_at,
        "milestones": [_serialize_milestone(ms) for ms in milestones],
    }


@router.get("/")
def list_all_ngos(
    page: int = 1,
    limit: int = 20,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    """Public: paginated NGO listing with search by name/description."""
    page = max(1, page)
    limit = max(1, min(limit, 100))

    query = db.query(NGO)
    if q:
        search = f"%{q.strip()}%"
        query = query.filter(NGO.name.ilike(search) | NGO.description.ilike(search))

    total_count = query.count()
    ngos = (
        query.order_by(NGO.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    data = [
        {
            "id": ngo.id,
            "user_id": ngo.user_id,
            "name": ngo.name,
            "description": ngo.description,
            "registration_number": ngo.registration_number,
            "address": ngo.address,
            "phone": ngo.phone,
            "website": ngo.website,
            "trust_score": ngo.trust_score,
            "campaign_count": ngo.campaign_count,
        }
        for ngo in ngos
    ]

    return {
        "data": data,
        "pagination": {
            "page": page,
            "limit": limit,
            "total_count": total_count,
            "has_more": page * limit < total_count,
        },
    }


@router.get("/discover")
def discover_ngos(
    page: int = 1,
    limit: int = 12,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    """Alias endpoint for frontend discovery pages."""
    return list_all_ngos(page=page, limit=limit, q=q, db=db)


# @router.post("/register")
# @router.post("/register")
# def register_ngo(
#     email: str,
#     password: str,
#     # name: str,
#     # description: str,
#     db: Session = Depends(get_db)
# ):
#     if db.query(User).filter(User.email == email).first():
#         raise HTTPException(400, "Email already exists")
#
#     hashed = hash_password(password)
#     user = User(email=email, password=hashed, role="ngo", is_active=False)
#     db.add(user)
#     db.commit()
#     db.refresh(user)
#
#     # ngo = NGO(
#     #     email=email,
#     #     password=hashed,
#     #     name=name,
#     #     description=description
#     # )
#     # db.add(ngo)
#     # db.commit()
#
#     return {"message": "NGO registered. Awaiting admin approval"}


@router.get("/me", response_model=None)
def my_ngo(current_user: User = Depends(ngo_required)):
    """Return basic profile for the logged-in NGO user."""
    return {
        "id":             NGO.id,
        "user_id":             current_user.id,
        "email":          current_user.email,
        "role":           current_user.role,
        "is_active":      current_user.is_active,
        "email_verified": current_user.email_verified,
    }


@router.post("/profile")
def create_profile(
    payload: NGOProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(ngo_required)
):
    existing = db.query(NGO).filter(NGO.user_id == current_user.id).first()
    if existing:
        raise HTTPException(400, "Profile already exists")

    ngo = NGO(
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
        registration_number=payload.registration_number,
        address=payload.address,
        phone=payload.phone,
        website=payload.website,
    )

    db.add(ngo)
    db.commit()

    return {"message": "Profile created"}

@router.put("/profile")
def update_profile(
    payload: NGOProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(ngo_required)
):
    # Fetch existing profile
    ngo = db.query(NGO).filter(NGO.user_id == current_user.id).first()
    if not ngo:
        raise HTTPException(404, "NGO profile not found")

    # Update fields if provided
    if payload.name is not None:
        ngo.name = payload.name
    if payload.description is not None:
        ngo.description = payload.description
    if payload.registration_number is not None:
        ngo.registration_number = payload.registration_number
    if payload.address is not None:
        ngo.address = payload.address
    if payload.phone is not None:
        ngo.phone = payload.phone
    if payload.website is not None:
        ngo.website = payload.website

    db.commit()
    db.refresh(ngo)

    return {"message": "Profile updated", "profile": {
        "name": ngo.name,
        "description": ngo.description,
        "registration_number": ngo.registration_number,
        "address": ngo.address,
        "phone": ngo.phone,
        "website": ngo.website
    }}


@router.get("/{ngo_id:int}")
def get_ngo_with_campaigns(ngo_id: int, db: Session = Depends(get_db)):
    """Public: get one NGO profile with all its campaigns and milestones."""
    ngo = db.query(NGO).filter(NGO.id == ngo_id).first()
    if not ngo:
        raise HTTPException(status_code=404, detail="NGO not found")

    campaigns = (
        db.query(Campaign)
        .filter(Campaign.ngo_id == ngo.id)
        .order_by(Campaign.created_at.desc())
        .all()
    )

    campaign_ids = [campaign.id for campaign in campaigns]
    milestones = []
    if campaign_ids:
        milestones = (
            db.query(Milestone)
            .filter(Milestone.campaign_id.in_(campaign_ids))
            .order_by(Milestone.campaign_id.asc(), Milestone.order_number.asc())
            .all()
        )

    milestone_map: dict[int, list[Milestone]] = {}
    for milestone in milestones:
        milestone_map.setdefault(milestone.campaign_id, []).append(milestone)

    return {
        "ngo": {
            "id": ngo.id,
            "user_id": ngo.user_id,
            "name": ngo.name,
            "description": ngo.description,
            "registration_number": ngo.registration_number,
            "address": ngo.address,
            "phone": ngo.phone,
            "website": ngo.website,
            "trust_score": ngo.trust_score,
            "campaign_count": ngo.campaign_count,
        },
        "campaigns": [
            _serialize_campaign(campaign, milestone_map.get(campaign.id, []))
            for campaign in campaigns
        ],
    }

