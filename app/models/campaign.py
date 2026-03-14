from sqlalchemy import Column, Integer, String, Float, ForeignKey, Text, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    id          = Column(Integer, primary_key=True)
    ngo_id      = Column(Integer, ForeignKey("ngos.id", ondelete="CASCADE"))

    title       = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    purpose     = Column(Text, nullable=False)
    image_url   = Column(String(500), nullable=False)

    target_amount = Column(Float, nullable=False)
    raised_amount = Column(Float, default=0.0, nullable=False)  # ← ADDED for dashboard
    status        = Column(String, default="draft")             # draft, active, paused

    created_at  = Column(DateTime(timezone=True), server_default=func.now())  # ← ADDED for dashboard

    milestones = relationship(
        "Milestone",
        back_populates="campaign",
        cascade="all, delete-orphan"
    )
