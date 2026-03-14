from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.db.base import Base


class PasswordResetToken(Base):
    """
    Stores one-time password-reset tokens.

    Columns
    -------
    token       : cryptographically random URL-safe string (hashed with SHA-256)
    expires_at  : naive UTC datetime — token is valid for PASSWORD_RESET_EXPIRE_MINUTES
    used_at     : set when the token is consumed; prevents reuse
    """
    __tablename__ = "password_reset_tokens"

    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String, unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    used_at    = Column(DateTime, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
