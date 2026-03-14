from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
import random
import threading
import time
from app.core.security import get_db
from app.core.roles import ngo_required
from app.models.campaign import Campaign
from app.models.milestone import Milestone
from app.models.ngo import NGO
from app.models.user import User
from pydantic import BaseModel, Field, field_validator
import cloudinary.uploader
from app.core.config import settings
from app.utils.cloudinary import upload
from fastapi import File, UploadFile


router = APIRouter(prefix="/campaigns", tags=["Campaigns"])


_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, list[dict]]] = {}
RANDOM_CACHE_TTL_SECONDS = 45

class CampaignCreate(BaseModel):
    title: str
    description: str
    purpose: str
    image_url: str
    target_amount: float


# @router.post("/")
# def create_campaign(
#     title: str,
#     target_amount: float,
#     ngo = Depends(ngo_required),
#     db: Session = Depends(get_db)
# ):
#     campaign = Campaign(
#         title=title,
#         target_amount=target_amount,
#         ngo_id=ngo.id
#     )
#     db.add(campaign)
#     db.commit()
#     return campaign

# @router.get("/")
# def list_campaigns(db: Session = Depends(get_db)):
#     return db.query(Campaign).filter(Campaign.status == "active").all()

# Cloudinary config
cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET
)

@router.get("/")
def list_campaigns(
    q: str | None = None,
    ngo_id: int | None = None,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """Public: list active campaigns with optional search and NGO filter."""
    limit = max(1, min(limit, 100))

    query = db.query(Campaign).filter(Campaign.status == "active")
    if ngo_id is not None:
        query = query.filter(Campaign.ngo_id == ngo_id)
    if q:
        search = f"%{q.strip()}%"
        query = query.filter(
            Campaign.title.ilike(search)
            | Campaign.description.ilike(search)
            | Campaign.purpose.ilike(search)
        )

    return query.order_by(Campaign.created_at.desc()).limit(limit).all()


def _serialize_milestone(milestone: Milestone) -> dict:
    return {
        "id": milestone.id,
        "title": milestone.title,
        "description": milestone.description,
        "target_amount": milestone.target_amount,
        "order_number": milestone.order_number,
        "status": milestone.status,
    }


def _serialize_campaign(campaign: Campaign, ngo_name: str | None = None) -> dict:
    return {
        "id": campaign.id,
        "ngo_id": campaign.ngo_id,
        "ngo_name": ngo_name,
        "title": campaign.title,
        "description": campaign.description,
        "purpose": campaign.purpose,
        "image_url": campaign.image_url,
        "target_amount": campaign.target_amount,
        "raised_amount": campaign.raised_amount,
        "status": campaign.status,
        "created_at": campaign.created_at,
    }


def _serialize_campaign_with_milestones(campaign: Campaign, milestones: list[Milestone], ngo_name: str | None = None) -> dict:
    return {
        "id": campaign.id,
        "ngo_id": campaign.ngo_id,
        "ngo_name": ngo_name,
        "title": campaign.title,
        "description": campaign.description,
        "purpose": campaign.purpose,
        "image_url": campaign.image_url,
        "target_amount": campaign.target_amount,
        "raised_amount": campaign.raised_amount,
        "status": campaign.status,
        "created_at": campaign.created_at,
        "milestones": [_serialize_milestone(m) for m in milestones],
    }


def _cache_get(key: str) -> list[dict] | None:
    now = time.time()
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        if not entry:
            return None
        expires_at, payload = entry
        if expires_at < now:
            _CACHE.pop(key, None)
            return None
        return payload


def _cache_set(key: str, payload: list[dict]) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (time.time() + RANDOM_CACHE_TTL_SECONDS, payload)


def _invalidate_random_caches() -> None:
    with _CACHE_LOCK:
        keys = [k for k in _CACHE.keys() if k.startswith("campaigns:")]
        for key in keys:
            _CACHE.pop(key, None)


@router.get("/trending/random")
def random_trending_campaigns(limit: int = 6, db: Session = Depends(get_db)):
    """Public: random campaigns picked from a trending-scored active pool."""
    limit = max(1, min(limit, 20))

    cache_key = f"campaigns:trending:{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    trend_score = func.coalesce(
        Campaign.raised_amount / func.nullif(Campaign.target_amount, 0),
        0.0,
    )

    pool_size = max(limit * 4, 20)
    campaigns = (
        db.query(Campaign)
        .filter(Campaign.status == "active")
        .order_by(desc(trend_score), desc(Campaign.raised_amount), desc(Campaign.created_at))
        .limit(pool_size)
        .all()
    )

    if len(campaigns) <= limit:
        selected = campaigns
    else:
        selected = random.sample(campaigns, k=limit)

    ngo_map = {
        ngo.id: ngo.name
        for ngo in db.query(NGO).filter(NGO.id.in_([c.ngo_id for c in selected])).all()
    }
    payload = [_serialize_campaign(campaign, ngo_name=ngo_map.get(campaign.ngo_id)) for campaign in selected]
    _cache_set(cache_key, payload)
    return payload


@router.get("/home/random")
def random_home_campaigns(limit: int = 8, db: Session = Depends(get_db)):
    """Public: random active campaigns for homepage cards."""
    limit = max(1, min(limit, 30))

    cache_key = f"campaigns:home:{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    campaigns = (
        db.query(Campaign)
        .filter(Campaign.status == "active")
        .order_by(func.random())
        .limit(limit)
        .all()
    )

    ngo_map = {
        ngo.id: ngo.name
        for ngo in db.query(NGO).filter(NGO.id.in_([c.ngo_id for c in campaigns])).all()
    }
    payload = [_serialize_campaign(campaign, ngo_name=ngo_map.get(campaign.ngo_id)) for campaign in campaigns]
    _cache_set(cache_key, payload)
    return payload


@router.get("/discover")
def discover_campaigns(
    page: int = 1,
    limit: int = 12,
    q: str | None = None,
    ngo_id: int | None = None,
    status: str = "active",
    db: Session = Depends(get_db),
):
    """Paginated campaign discovery endpoint for frontend lists."""
    page = max(1, page)
    limit = max(1, min(limit, 100))

    query = db.query(Campaign)
    if status != "all":
        query = query.filter(Campaign.status == status)
    if ngo_id is not None:
        query = query.filter(Campaign.ngo_id == ngo_id)
    if q:
        search = f"%{q.strip()}%"
        query = query.filter(
            Campaign.title.ilike(search)
            | Campaign.description.ilike(search)
            | Campaign.purpose.ilike(search)
        )

    total_count = query.count()
    campaigns = (
        query.order_by(Campaign.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    ngo_map = {
        ngo.id: ngo.name
        for ngo in db.query(NGO).filter(NGO.id.in_([c.ngo_id for c in campaigns])).all()
    }

    return {
        "data": [_serialize_campaign(campaign, ngo_name=ngo_map.get(campaign.ngo_id)) for campaign in campaigns],
        "pagination": {
            "page": page,
            "limit": limit,
            "total_count": total_count,
            "has_more": page * limit < total_count,
        },
    }


@router.get("/with-milestones")
def all_campaigns_with_milestones(
    page: int = 1,
    limit: int = 20,
    q: str | None = None,
    ngo_id: int | None = None,
    status: str = "all",
    db: Session = Depends(get_db),
):
    """Public/Admin utility: paginated campaigns with full milestone info."""
    page = max(1, page)
    limit = max(1, min(limit, 100))

    query = db.query(Campaign)
    if status != "all":
        query = query.filter(Campaign.status == status)
    if ngo_id is not None:
        query = query.filter(Campaign.ngo_id == ngo_id)
    if q:
        search = f"%{q.strip()}%"
        query = query.filter(
            Campaign.title.ilike(search)
            | Campaign.description.ilike(search)
            | Campaign.purpose.ilike(search)
        )

    total_count = query.count()
    campaigns = (
        query.order_by(Campaign.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    if not campaigns:
        return {
            "data": [],
            "pagination": {
                "page": page,
                "limit": limit,
                "total_count": total_count,
                "has_more": False,
            },
        }

    campaign_ids = [c.id for c in campaigns]

    milestones = (
        db.query(Milestone)
        .filter(Milestone.campaign_id.in_(campaign_ids))
        .order_by(Milestone.campaign_id.asc(), Milestone.order_number.asc())
        .all()
    )

    ngo_map = {
        ngo.id: ngo.name
        for ngo in db.query(NGO).filter(NGO.id.in_([c.ngo_id for c in campaigns])).all()
    }

    milestone_map: dict[int, list[Milestone]] = {}
    for milestone in milestones:
        milestone_map.setdefault(milestone.campaign_id, []).append(milestone)

    return {
        "data": [
            _serialize_campaign_with_milestones(
                campaign,
                milestone_map.get(campaign.id, []),
                ngo_name=ngo_map.get(campaign.ngo_id),
            )
            for campaign in campaigns
        ],
        "pagination": {
            "page": page,
            "limit": limit,
            "total_count": total_count,
            "has_more": page * limit < total_count,
        },
    }


MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB in bytes

def validate_file_size(file: UploadFile):
    file.file.seek(0, 2)  # go to end of file
    size = file.file.tell()  # get current position = file size
    file.file.seek(0)  # reset pointer to start
    if size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Max allowed size is {MAX_FILE_SIZE / (1024*1024)} MB"
        )

@router.post("/campaign")
def create_campaign(
    title: str,
    description: str,
    purpose: str,
    target_amount: float,
    file: UploadFile = File(...),  # file upload
    db: Session = Depends(get_db),
    current_user: User = Depends(ngo_required)
):
    ngo = db.query(NGO).filter(NGO.user_id == current_user.id).first()
    if not ngo:
        raise HTTPException(400, "Complete NGO profile first")
    
     # Validate file size
    validate_file_size(file)
    
    # Upload image to Cloudinary
   
    image_url = upload(file, folder="g4")


    campaign = Campaign(
        ngo_id=ngo.id,
        title=title,
        description=description,
        purpose=purpose,
        image_url=image_url,
        target_amount=target_amount,
    )

    db.add(campaign)
    ngo.campaign_count += 1
    db.commit()
    _invalidate_random_caches()

    return {"message": "Campaign created", "campaign_id": campaign.id, "image_url": image_url}






@router.put("/campaign/{campaign_id}")
def update_campaign(
    campaign_id: int,
    payload: CampaignCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(ngo_required)
):
    campaign = db.query(Campaign).get(campaign_id)

    if not campaign:
        raise HTTPException(404, "Campaign not found")

    campaign.title = payload.title
    campaign.description = payload.description
    campaign.purpose = payload.purpose
    campaign.image_url = payload.image_url
    campaign.target_amount = payload.target_amount

    db.commit()
    _invalidate_random_caches()
    return {"message": "Campaign updated"}


@router.delete("/campaign/{campaign_id}")
def delete_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(ngo_required)
):
    campaign = db.query(Campaign).get(campaign_id)
    if not campaign:
        raise HTTPException(404, "Not found")

    db.delete(campaign)
    db.commit()
    _invalidate_random_caches()

    return {"message": "Campaign deleted"}

