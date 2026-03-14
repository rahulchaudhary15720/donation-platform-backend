from sqlalchemy import Column, Integer, Text, ForeignKey, DateTime
from sqlalchemy.sql import func
from app.db.base import Base

class EmailNotification(Base):
    __tablename__ = "email_notifications"
    id = Column(Integer, primary_key=True)
    donation_id = Column(Integer, ForeignKey("donations.id", ondelete="CASCADE"))
    encrypted_email = Column(Text, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
