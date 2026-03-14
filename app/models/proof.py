from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from app.db.base import Base
from sqlalchemy.orm import relationship

class Proof(Base):
    __tablename__ = "proofs"
    id = Column(Integer, primary_key=True)
    milestone_id = Column(Integer, ForeignKey("milestones.id"))
    file_url = Column(String)
    verified = Column(Boolean, default=False)

    milestone = relationship("Milestone", back_populates="proofs")
