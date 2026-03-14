from sqlalchemy import Column, Integer, String, Float, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.db.base import Base


class Milestone(Base):
    __tablename__ = "milestones"

    id          = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"))

    title       = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)

    target_amount = Column(Float, nullable=False)
    order_number  = Column(Integer, nullable=False)
    status        = Column(String, default="locked")  # active, locked

    campaign = relationship("Campaign", back_populates="milestones")
    proofs   = relationship("Proof", back_populates="milestone", cascade="all, delete-orphan")
