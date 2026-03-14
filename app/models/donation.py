from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class Donation(Base):
    __tablename__ = "donations"

    id             = Column(Integer, primary_key=True, index=True)
    campaign_id    = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    milestone_id   = Column(Integer, ForeignKey("milestones.id"), nullable=False)
    user_id        = Column(Integer, ForeignKey("users.id"), nullable=True)
    hashed_email   = Column(String, nullable=True)
    transaction_id = Column(String, unique=True, index=True, nullable=False)
    amount         = Column(Float, nullable=False)
    is_anonymous   = Column(Boolean, default=False, nullable=False)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    # Needed for user dashboard joinedload
    campaign  = relationship("Campaign",  foreign_keys=[campaign_id])
    milestone = relationship("Milestone", foreign_keys=[milestone_id])
