# from sqlalchemy import Column, Integer, String, Text
# from app.db.base import Base
# # from sqlalchemy import ForeignKey
# # from sqlalchemy.orm import relationship

# class NGO(Base):
#     __tablename__ = "ngos"

#     id = Column(Integer, primary_key=True)
#     # user_id = Column(Integer, ForeignKey("users.id"), unique=True)
#     # name = Column(String, nullable=False)
#     # description = Column(Text)
#     # trust_score = Column(Integer, default=100)
#     # status = Column(String, default="pending")
#     email = Column(String, unique=True, nullable=False)
#     password = Column(String, nullable=False)
#     # user = relationship("User")
# app/models/ngo.py

from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base import Base

class NGO(Base):
    __tablename__ = "ngos"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    registration_number = Column(String(100), nullable=False)
    address = Column(Text, nullable=False)
    phone = Column(String(50), nullable=False)
    website = Column(String(255), nullable=True)

    trust_score = Column(Integer, default=100)
    campaign_count = Column(Integer, default=0)

    user = relationship("User")
