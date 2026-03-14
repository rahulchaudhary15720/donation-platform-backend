from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id                    = Column(Integer, primary_key=True)
    email                 = Column(String, unique=True, nullable=False)
    password              = Column(String, nullable=False)
    role                  = Column(String, default="user")        # user, ngo, admin
    full_name             = Column(String(100), nullable=True)    # ← ADDED
    phone                 = Column(String(25),  nullable=True)    # ← ADDED
    is_active             = Column(Boolean, default=True)
    email_verified        = Column(Boolean, default=False)
    failed_login_attempts = Column(Integer, default=0)
    locked_until          = Column(DateTime, nullable=True)
    last_login_at         = Column(DateTime(timezone=True), nullable=True)
    created_at            = Column(DateTime(timezone=True), server_default=func.now())
    updated_at            = Column(DateTime(timezone=True), onupdate=func.now())
