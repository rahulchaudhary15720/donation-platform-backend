"""
Pydantic request models for the /auth router.

Keeping schema definitions in a dedicated module ensures auth.py stays focused
on business logic and makes these models independently importable and testable.
"""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RegisterRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    role: Literal["user", "ngo"]

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        email = value.strip().lower()
        if email.count("@") != 1:
            raise ValueError("Invalid email")
        return email

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        # At least 1 upper, 1 lower, 1 digit, 1 special
        if not re.search(r"[A-Z]", value):
            raise ValueError("Password must include an uppercase letter")
        if not re.search(r"[a-z]", value):
            raise ValueError("Password must include a lowercase letter")
        if not re.search(r"[0-9]", value):
            raise ValueError("Password must include a number")
        if not re.search(r"[^A-Za-z0-9]", value):
            raise ValueError("Password must include a special character")
        return value

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, value: str) -> str:
        return str(value).strip().lower()


class LoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=128)
    role: Literal["user", "ngo", "admin"]

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        email = value.strip().lower()
        if email.count("@") != 1:
            raise ValueError("Invalid email")
        return email

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, value: str) -> str:
        return str(value).strip().lower()


class RefreshRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    refresh_token: str = Field(min_length=20, max_length=512)


class VerifyEmailRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    token: str = Field(min_length=20, max_length=128)


class ResendVerificationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    email: str = Field(min_length=5, max_length=254)


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    email: str = Field(min_length=5, max_length=254)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        email = value.strip().lower()
        if email.count("@") != 1:
            raise ValueError("Invalid email")
        return email


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    token: str = Field(min_length=20, max_length=256)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not re.search(r"[A-Z]", value):
            raise ValueError("Password must include an uppercase letter")
        if not re.search(r"[a-z]", value):
            raise ValueError("Password must include a lowercase letter")
        if not re.search(r"[0-9]", value):
            raise ValueError("Password must include a number")
        if not re.search(r"[^A-Za-z0-9]", value):
            raise ValueError("Password must include a special character")
        return value


# ================================================================
#  USER DASHBOARD SCHEMAS  — appended, do not modify above
# ================================================================
from typing import Optional, List
from datetime import datetime, date


class UserProfileResponse(BaseModel):
    id:             int
    email:          str
    full_name:      Optional[str] = None
    phone:          Optional[str] = None
    role:           str
    is_active:      bool
    email_verified: bool
    last_login_at:  Optional[datetime] = None
    created_at:     Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class UserUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    phone:     Optional[str] = None
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v):
        if v is not None:
            v = v.strip()
            if len(v) < 2:
                raise ValueError("Full name must be at least 2 characters")
            if len(v) > 100:
                raise ValueError("Full name cannot exceed 100 characters")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        if v is not None:
            v = v.strip()
            # Accepts: +91 9876543210 / +1 9876543210 / 9876543210 / 09876543210
            if not re.match(r'^\+?[\d\s\-\(\)]{7,20}$', v):
                raise ValueError("Must be a valid phone number (7–20 digits, optional +, spaces, dashes)")
        return v



class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password:     str
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @field_validator("new_password")
    @classmethod
    def validate_strength(cls, v):
        errors = []
        if len(v) < 8:                             errors.append("at least 8 characters")
        if not re.search(r"[A-Z]", v):             errors.append("one uppercase letter")
        if not re.search(r"[a-z]", v):             errors.append("one lowercase letter")
        if not re.search(r"[0-9]", v):             errors.append("one digit")
        if not re.search(r"[^A-Za-z0-9]", v):     errors.append("one special character")
        if errors:
            raise ValueError(f"Password must contain: {', '.join(errors)}")
        return v


class DonationStatsResponse(BaseModel):
    total_donated:       float
    total_donations:     int
    campaigns_supported: int
    this_month_donated:  float
    first_donation_date: Optional[date] = None
    model_config = ConfigDict(from_attributes=True)


class CampaignMini(BaseModel):
    id:    int
    title: str
    model_config = ConfigDict(from_attributes=True)


class DonationOut(BaseModel):
    id:             int
    transaction_id: str
    amount:         float
    is_anonymous:   bool
    campaign_id:    int
    campaign:       Optional[CampaignMini] = None
    created_at:     Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class PaginatedDonationsResponse(BaseModel):
    data:        List[DonationOut]
    total_count: int
    page:        int
    limit:       int
    total_pages: int
    has_more:    bool


# ================================================================
#  PAYMENT SCHEMAS
# ================================================================

class PaymentInitiateRequest(BaseModel):
    """Body sent by frontend to create a payment order."""
    campaign_id:  int   = Field(..., gt=0)
    milestone_id: int   = Field(..., gt=0)
    amount:       float = Field(..., gt=0, le=1_000_000, description="Amount in INR, max ₹10,00,000")
    is_anonymous: bool  = False
    email:        Optional[str] = Field(None, max_length=254, description="Required only for anonymous donations that want a receipt")
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip().lower()
            if v.count("@") != 1:
                raise ValueError("Invalid email address")
        return v


class PaymentInitiateResponse(BaseModel):
    """Returned to frontend — frontend shows the mock/real payment modal."""
    order_id:    str
    amount:      float
    currency:    str = "INR"
    gateway:     str
    # Mock-only fields (real Razorpay would use these same field names)
    key:         str   = "mock_key"
    description: str
    # ── Mock-only extra fields ──────────────────────────────────────────────
    # In prod these would NOT be returned; Razorpay SDK handles them internally.
    # Included here so the frontend can call /verify without a real payment modal.
    # Field names intentionally mirror Razorpay's callback payload for easy swap.
    mock_payment_id: Optional[str] = None
    mock_signature:  Optional[str] = None


class PaymentVerifyRequest(BaseModel):
    """
    Body sent by frontend after the payment modal completes.

    Mock flow:
        frontend receives order_id from initiate → shows fake modal →
        calls verify with order_id + mock_payment_id (any non-empty string).

    Real Razorpay flow (drop-in replacement):
        frontend receives order_id → Razorpay SDK auto-fills
        razorpay_payment_id and razorpay_signature → same verify call.
    """
    order_id:    str = Field(..., min_length=10, max_length=64)
    payment_id:  str = Field(..., min_length=1,  max_length=64,
                              description="mock: any string | razorpay: razorpay_payment_id")
    signature:   str = Field(..., min_length=1,  max_length=128,
                              description="mock: HMAC-SHA256(order_id|payment_id, JWT_SECRET) | razorpay: razorpay_signature")
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class PaymentVerifyResponse(BaseModel):
    """Returned after a successful payment verification."""
    message:        str
    transaction_id: str
    amount:         float
    campaign:       str
    milestone:      str
