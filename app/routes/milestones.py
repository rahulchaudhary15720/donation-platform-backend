from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.security import get_db
from app.core.roles import ngo_required
from app.models.milestone import Milestone
from app.models.campaign import Campaign
from app.models.ngo import NGO
from app.models.user import User
from app.models.proof import Proof
from typing import List
from fastapi import status
from fastapi import File, UploadFile
from app.utils.cloudinary import upload


router = APIRouter(prefix="/campaigns", tags=["Milestones"])

# router = APIRouter(prefix="/milestones", tags=["Milestones"])

# @router.post("/{milestone_id}/upload-proof")
# def upload_proof(
#     milestone_id: int,
#     file: UploadFile = File(...),
#     ngo = Depends(ngo_required),
#     db: Session = Depends(get_db)
# ):
#     milestone = db.query(Milestone).get(milestone_id)
#     if not milestone:
#         raise HTTPException(404, "Milestone not found")

#     # (Optional but recommended) check milestone belongs to NGO
#     # campaign = db.query(Campaign).get(milestone.campaign_id)
#     # if campaign.ngo_id != ngo.id:
#     #     raise HTTPException(403)

#     file_url = upload(file, folder="milestone_proofs")

#     proof = Proof(
#         milestone_id=milestone_id,
#         file_url=file_url,
#         verified=False
#     )

#     db.add(proof)
#     db.commit()

#     milestone.status = "awaiting_verification"
#     db.commit()

#     return {
#         "message": "Proof uploaded successfully",
#         "proof_url": file_url
#     }
from pydantic import BaseModel

class MilestoneCreate(BaseModel):
    title: str
    description: str
    target_amount: float




# @router.post("/{campaign_id}/milestones")
# def create_milestone(
#     campaign_id: int,
#     payload: MilestoneCreate,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(ngo_required)
# ):
#     # Get NGO
#     ngo = db.query(NGO).filter(NGO.user_id == current_user.id).first()
#     if not ngo:
#         raise HTTPException(400, "NGO profile not found")

#     # Get Campaign
#     campaign = db.query(Campaign).get(campaign_id)
#     if not campaign:
#         raise HTTPException(404, "Campaign not found")

#     # Ownership check
#     if campaign.ngo_id != ngo.id:
#         raise HTTPException(403, "Not allowed")

#     # Count existing milestones
#     existing_count = db.query(Milestone)\
#         .filter(Milestone.campaign_id == campaign_id)\
#         .count()

#     milestone = Milestone(
#         campaign_id=campaign_id,
#         title=payload.title,
#         description=payload.description,
#         target_amount=payload.target_amount,
#         order_number=existing_count + 1,
#         status="active" if existing_count == 0 else "locked"
#     )

#     db.add(milestone)
#     db.commit()

#     return {
#         "message": "Milestone created",
#         "milestone_id": milestone.id,
#         "order_number": milestone.order_number
#     }



# @router.post("/{campaign_id}/milestones/batch")
# def create_milestones(
#     campaign_id: int,
#     payload: List[MilestoneCreate],  # <-- now a list
#     db: Session = Depends(get_db),
#     current_user: User = Depends(ngo_required)
# ):
    
#     # Enforce minimum 3 milestones
#     if len(payload) < 3:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="At least 3 milestones are required"
#         )
    
#     # Get NGO
#     ngo = db.query(NGO).filter(NGO.user_id == current_user.id).first()
#     if not ngo:
#         raise HTTPException(400, "NGO profile not found")

#     # Get Campaign
#     campaign = db.query(Campaign).get(campaign_id)
#     if not campaign:
#         raise HTTPException(404, "Campaign not found")

#     # Ownership check
#     if campaign.ngo_id != ngo.id:
#         raise HTTPException(403, "Not allowed")

#     # Count existing milestones
#     existing_count = db.query(Milestone)\
#         .filter(Milestone.campaign_id == campaign_id)\
#         .count()

#     created_milestones = []

#     for i, m_data in enumerate(payload):
#         milestone = Milestone(
#             campaign_id=campaign_id,
#             title=m_data.title,
#             description=m_data.description,
#             target_amount=m_data.target_amount,
#             order_number=existing_count + i + 1,
#             status="active" if existing_count + i == 0 else "locked"
#         )
#         db.add(milestone)
#         created_milestones.append(milestone)

#     db.commit()

#     # Return all created milestones
#     return {
#         "message": f"{len(created_milestones)} milestones created",
#         "milestones": [
#             {"id": m.id, "order_number": m.order_number, "title": m.title}
#             for m in created_milestones
#         ]
#     }

@router.post("/{campaign_id}/milestones/batch")
def create_milestones(
    campaign_id: int,
    payload: List[MilestoneCreate],
    db: Session = Depends(get_db),
    current_user: User = Depends(ngo_required)
):

    # Get NGO
    ngo = db.query(NGO).filter(NGO.user_id == current_user.id).first()
    if not ngo:
        raise HTTPException(400, "NGO profile not found")

    # Get Campaign
    campaign = db.query(Campaign).get(campaign_id)
    if not campaign:
        raise HTTPException(404, "Campaign not found")

    # Ownership check
    if campaign.ngo_id != ngo.id:
        raise HTTPException(403, "Not allowed")

    # Count existing milestones
    existing_count = db.query(Milestone)\
        .filter(Milestone.campaign_id == campaign_id)\
        .count()

    # Enforce minimum 3 milestones only for new campaigns
    if existing_count == 0 and len(payload) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least 3 milestones are required for a new campaign"
        )

    created_milestones = []

    for i, m_data in enumerate(payload):
        milestone = Milestone(
            campaign_id=campaign_id,
            title=m_data.title,
            description=m_data.description,
            target_amount=m_data.target_amount,
            order_number=existing_count + i + 1,
            status="active" if existing_count + i == 0 else "locked"
        )
        db.add(milestone)
        created_milestones.append(milestone)

    db.commit()

    return {
        "message": f"{len(created_milestones)} milestones created",
        "milestones": [
            {"id": m.id, "order_number": m.order_number, "title": m.title}
            for m in created_milestones
        ]
    }



@router.put("/milestones/{milestone_id}")
def update_milestone(
    milestone_id: int,
    payload: MilestoneCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(ngo_required)
):
    milestone = db.query(Milestone).get(milestone_id)
    if not milestone:
        raise HTTPException(404, "Milestone not found")

    campaign = db.query(Campaign).get(milestone.campaign_id)
    ngo = db.query(NGO).filter(NGO.user_id == current_user.id).first()

    if campaign.ngo_id != ngo.id:
        raise HTTPException(403, "Not allowed")

    milestone.title = payload.title
    milestone.description = payload.description
    milestone.target_amount = payload.target_amount

    db.commit()
    return {"message": "Milestone updated"}


@router.delete("/milestones/{milestone_id}")
def delete_milestone(
    milestone_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(ngo_required)
):
    milestone = db.query(Milestone).get(milestone_id)
    if not milestone:
        raise HTTPException(404, "Milestone not found")

    campaign = db.query(Campaign).get(milestone.campaign_id)
    ngo = db.query(NGO).filter(NGO.user_id == current_user.id).first()

    if campaign.ngo_id != ngo.id:
        raise HTTPException(403, "Not allowed")

    # Count milestones for this campaign
    milestone_count = db.query(Milestone).filter(Milestone.campaign_id == campaign.id).count()

    # Prevent deletion if there are only 3 milestones
    if milestone_count <= 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete milestone. A campaign must have at least 3 milestones."
        )

    db.delete(milestone)
    db.commit()

    return {"message": "Milestone deleted"}


# -------------------------------
# Upload proof for a milestone
# -------------------------------


MAX_FILE_SIZE = 1 * 1024 * 1024  # 1 MB


@router.post("/{milestone_id}/upload-proof")
def upload_proof(
    milestone_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(ngo_required)
):
    milestone = db.query(Milestone).get(milestone_id)
    if not milestone:
        raise HTTPException(404, "Milestone not found")

    # Ownership check
    campaign = db.query(Campaign).get(milestone.campaign_id)
    ngo = db.query(NGO).filter(NGO.user_id == current_user.id).first()
    if campaign.ngo_id != ngo.id:
        raise HTTPException(403, "Not allowed")

    # File size check
    file.file.seek(0, 2)  # go to end
    file_size = file.file.tell()
    file.file.seek(0)  # reset pointer
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(400, "File too large. Max 1 MB allowed.")

    file_url = upload(file, folder="milestone_proofs")

    proof = Proof(milestone_id=milestone.id, file_url=file_url, verified=False)
    db.add(proof)
    db.commit()

    # Mark milestone as awaiting verification
    milestone.status = "standby"  # still locked until approved
    db.commit()

    return {"message": "Proof uploaded", "proof_url": file_url}

