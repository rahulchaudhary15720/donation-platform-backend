from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from app.db.base import Base


class PaymentOrder(Base):
    """
    Represents a pending payment intent before a donation is confirmed.

    Lifecycle:  pending ──► paid   (on successful verify)
                         └──► failed (on explicit failure or expiry)

    This table is the bridge between "user clicked Donate" and
    "donation row exists in donations table".  The donations row is
    only created after payment is verified — no phantom donations.
    """
    __tablename__ = "payment_orders"

    id              = Column(Integer, primary_key=True, index=True)

    # Who is paying and for what
    user_id         = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    campaign_id     = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    milestone_id    = Column(Integer, ForeignKey("milestones.id", ondelete="CASCADE"), nullable=False)

    # Payment details
    amount          = Column(Float, nullable=False)
    is_anonymous    = Column(Boolean, default=False, nullable=False)
    anonymous_email = Column(Text, nullable=True)  # Fernet-encrypted if provided

    # Gateway fields (mock now, real Razorpay / Stripe later)
    order_id        = Column(String(64), unique=True, nullable=False, index=True)   # MOCK_ORDER_xxx
    payment_id      = Column(String(64), nullable=True)                              # filled on verify
    gateway         = Column(String(32), default="mock", nullable=False)             # "mock" | "razorpay"
    status          = Column(String(16), default="pending", nullable=False)          # pending | paid | failed

    # Timestamps
    expires_at      = Column(DateTime, nullable=False)   # order is invalid after this
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())

    # Back-reference: once paid this links to the created donation
    donation_id     = Column(Integer, ForeignKey("donations.id", ondelete="SET NULL"), nullable=True)
