from fastapi import APIRouter, Depends, HTTPException, Response, Request
from datetime import datetime, timedelta, timezone
import hashlib
import logging
import secrets
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.security import (
    get_db, hash_password, verify_password, create_access_token
)
from app.core.config import settings
from app.core.rate_limit import rate_limit
from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.models.email_verification import EmailVerification
from app.models.password_reset import PasswordResetToken
from app.utils.email_verification_service import (
    generate_verification_token, send_verification_email, send_welcome_email,
    send_password_reset_email,
)
from app.helper.pydantic_helper import (
    RegisterRequest,
    LoginRequest,
    RefreshRequest,
    VerifyEmailRequest,
    ResendVerificationRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])

REGISTER_ROLES = {"user", "ngo"}
LOGIN_ROLES = {"user", "ngo", "admin"}
PASSWORD_RESET_EXPIRE_MINUTES = 30
DUMMY_HASH = hash_password("not_the_password")  # Mitigates timing attacks when user is not found


def _utcnow() -> datetime:
    """Return the current UTC time as a timezone-naive datetime.

    All DateTime columns in the models are declared without timezone=True, so
    SQLAlchemy returns naive datetimes on reads. Comparing a naive DB value to a
    timezone-aware datetime.now(timezone.utc) raises TypeError at runtime. This
    helper keeps all datetime arithmetic consistent with the DB storage format
    while still deriving the value from the modern, non-deprecated API.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)

def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def _issue_refresh_token(user_id: int, db: Session) -> str:
    raw = secrets.token_urlsafe(48)
    token_hash = _hash_refresh_token(raw)
    expires_at = _utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    db.add(
        RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            revoked_at=None,
        )
    )
    db.commit()
    return raw

def _is_locked(user: User) -> bool:
    return bool(user.locked_until and user.locked_until > _utcnow())

def _reset_lock(user: User):
    user.failed_login_attempts = 0
    user.locked_until = None

def _register_failed_login(user: User, db: Session):
    user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
    if user.failed_login_attempts >= settings.MAX_LOGIN_ATTEMPTS:
        user.locked_until = _utcnow() + timedelta(minutes=settings.LOCKOUT_MINUTES)
        user.failed_login_attempts = 0
    db.commit()

def _authenticate_user(email: str, password: str, role: str | None, db: Session) -> User:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        verify_password(password, DUMMY_HASH)
        raise HTTPException(401, "Invalid credentials")

    if user.locked_until and user.locked_until <= _utcnow():
        _reset_lock(user)
        db.commit()

    if _is_locked(user):
        raise HTTPException(403, "Account locked. Try again later")

    if not verify_password(password, user.password):
        _register_failed_login(user, db)
        raise HTTPException(401, "Invalid credentials")

    if role is not None and user.role != role:
        _register_failed_login(user, db)
        raise HTTPException(401, "Invalid credentials")

    if not user.email_verified:
        raise HTTPException(403, "Email not verified. Please check your inbox.")

    if not user.is_active:
        raise HTTPException(403, "Account not activated")

    _reset_lock(user)
    user.last_login_at = _utcnow()
    db.commit()
    return user

@router.post("/register", dependencies=[Depends(rate_limit("auth:register", limit=3, window_seconds=60))])
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    # NOTE: payload.role is already constrained to REGISTER_ROLES by Pydantic Literal.
    # NOTE: We rely on the DB unique constraint as the authoritative uniqueness check rather
    # than a pre-flight SELECT, which has a TOCTOU race condition under concurrent requests.
    # The SELECT below is kept purely as a fast-path to return a clean 400 before hashing;
    # the IntegrityError catch below is the real guard.
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(400, "Email already registered")

    is_active = payload.role != "ngo"
    user = User(
        email=payload.email,
        password=hash_password(payload.password),
        role=payload.role,
        is_active=is_active,
        email_verified=False,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(400, "Email already registered")
    db.refresh(user)

    # Persist the verification token — this must succeed before we attempt email delivery.
    # Keeping DB work and network I/O in separate try blocks prevents a misleading state
    # where the user exists but has no verification token due to an SMTP failure being
    # silently swallowed alongside the DB commit.
    verification_token = generate_verification_token()
    try:
        expires_at = _utcnow() + timedelta(hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS)
        email_verification = EmailVerification(
            user_id=user.id,
            token=verification_token,
            expires_at=expires_at,
        )
        db.add(email_verification)
        db.commit()
    except Exception as e:
        logger.error("Failed to persist verification token for user_id=%s: %s", user.id, e)
        db.rollback()
        raise HTTPException(500, "Registration succeeded but we could not create a verification token. Please use resend-verification.")

    # Email delivery is best-effort — token is already safely in the DB.
    try:
        send_verification_email(payload.email, verification_token)
    except Exception as e:
        logger.error("Failed to send verification email to user_id=%s: %s", user.id, e)
        return {
            "message": f"{payload.role} registered. Verification email could not be sent — use /auth/resend-verification.",
            "email": payload.email,
        }

    return {
        "message": f"{payload.role} registered successfully. Please check your email to verify your account.",
        "email": payload.email,
    }

@router.post("/login", dependencies=[Depends(rate_limit("auth:login", limit=5, window_seconds=60))])
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    # NOTE: payload.role is already constrained to LOGIN_ROLES by Pydantic Literal.
    user = _authenticate_user(payload.email, payload.password, payload.role, db)
    token = create_access_token({"sub": str(user.id), "role": user.role, "type": "access"})
    refresh_token = _issue_refresh_token(user.id, db)
    
    # Set the refresh token securely in an HttpOnly cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax",  # Or 'strict' depending on your frontend-backend setup
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )
    
    return {
        "access_token": token,
        "token_type": "bearer",
        # We optionally return refresh_token in body for Swagger testing ease, 
        # but the frontend should rely on the cookie
        "refresh_token": refresh_token 
    }

@router.post("/refresh", dependencies=[Depends(rate_limit("auth:refresh", limit=10, window_seconds=60))])
def refresh(request: Request, response: Response, payload: RefreshRequest | None = None, db: Session = Depends(get_db)):
    # Fallback: check cookie first, then json payload
    token_to_refresh = request.cookies.get("refresh_token")
    if not token_to_refresh and payload:
        token_to_refresh = payload.refresh_token
        
    if not token_to_refresh:
        raise HTTPException(401, "Refresh token missing")

    token_hash = _hash_refresh_token(token_to_refresh)
    stored = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == token_hash)
        .first()
    )
    if not stored or stored.revoked_at is not None:
        response.delete_cookie("refresh_token")
        raise HTTPException(401, "Invalid refresh token")
    if stored.expires_at <= _utcnow():
        response.delete_cookie("refresh_token")
        raise HTTPException(401, "Refresh token expired")

    # Rotate refresh token
    stored.revoked_at = _utcnow()
    db.commit()

    user = db.get(User, stored.user_id)
    if not user:
        raise HTTPException(401, "Invalid refresh token")
    if not user.is_active:
        raise HTTPException(403, "Account not activated")
        
    access_token = create_access_token({"sub": str(stored.user_id), "role": user.role, "type": "access"})
    new_refresh = _issue_refresh_token(stored.user_id, db)
    
    # Set the new refresh token as a cookie
    response.set_cookie(
        key="refresh_token",
        value=new_refresh,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )
    
    return {
        "access_token": access_token,
        "refresh_token": new_refresh, # Kept for Swagger UI compatibility
        "token_type": "bearer",
    }

@router.post("/logout", dependencies=[Depends(rate_limit("auth:logout", limit=10, window_seconds=60))])
def logout(request: Request, response: Response, payload: RefreshRequest | None = None, db: Session = Depends(get_db)):
    # Check cookie first, fallback to payload
    token_to_refresh = request.cookies.get("refresh_token")
    if not token_to_refresh and payload:
        token_to_refresh = payload.refresh_token
        
    if token_to_refresh:
        token_hash = _hash_refresh_token(token_to_refresh)
        stored = (
            db.query(RefreshToken)
            .filter(RefreshToken.token_hash == token_hash)
            .first()
        )
        if stored and stored.revoked_at is None:
            stored.revoked_at = _utcnow()
            db.commit()
            
    # Clear the cookie
    response.delete_cookie("refresh_token")
    
    return {"message": "Logged out"}

@router.post("/verify-email", dependencies=[Depends(rate_limit("auth:verify", limit=5, window_seconds=60))])
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    """Verify user's email address using the verification token"""
    verification = (
    db.query(EmailVerification)
    .filter(EmailVerification.token == payload.token)
    .first()  # get record even if verified
    )

    user_email = None
    if verification:
        user = db.get(User, verification.user_id)
        if user:
            user_email = user.email

    # Check if token is invalid or already used
    if not verification or verification.verified_at is not None:
        raise HTTPException(
            400,
            detail={
                "message": "Invalid or already used verification token",
                "email": user_email  # now includes email if available
            }
        )

    # Check if token expired
    if verification.expires_at < _utcnow():
        raise HTTPException(
            400,
            detail={
                "message": "Verification token has expired",
                "email": user_email
            }
        )

    # Mark as verified
    verification.verified_at = _utcnow()

    # Update user
    user = db.get(User, verification.user_id)
    if not user:
        raise HTTPException(404, "User not found")
    
    user.email_verified = True
    db.commit()
    
    # Send welcome email
    try:
        send_welcome_email(user.email, user.role)
    except Exception as e:
        logger.error("Failed to send welcome email to user_id=%s: %s", user.id, e)
    
    return {
        "message": "Email verified successfully",
        "email": user.email,
        "role": user.role
    }

@router.post("/resend-verification", dependencies=[Depends(rate_limit("auth:resend", limit=3, window_seconds=300))])
def resend_verification(payload: ResendVerificationRequest, db: Session = Depends(get_db)):
    """Resend verification email to user"""
    user = db.query(User).filter(User.email == payload.email).first()
    
    if not user or user.email_verified:
        # Return the same response whether the user doesn't exist OR is already verified.
        # Raising HTTP 400 only for verified accounts would reveal that the email
        # exists and is verified — an enumeration vector.
        return {"message": "If the email exists and is unverified, a new verification link has been sent"}
    
    # Invalidate old tokens by deleting them
    db.query(EmailVerification)\
        .filter(EmailVerification.user_id == user.id)\
        .filter(EmailVerification.verified_at.is_(None))\
        .delete()
    
    # Generate new token
    verification_token = generate_verification_token()
    expires_at = _utcnow() + timedelta(hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS)

    email_verification = EmailVerification(
        user_id=user.id,
        token=verification_token,
        expires_at=expires_at,
    )
    db.add(email_verification)
    db.commit()

    # Send email
    try:
        send_verification_email(user.email, verification_token)
    except Exception as e:
        logger.error("Failed to resend verification email to user_id=%s: %s", user.id, e)
        raise HTTPException(503, "Failed to send verification email")

    return {"message": "Verification email sent successfully"}

@router.get("/verification-status/{email}", dependencies=[Depends(rate_limit("auth:verification_status", limit=10, window_seconds=60))])
def check_verification_status(email: str, db: Session = Depends(get_db)):
    """Check if an email is verified (public endpoint for UX)"""
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    
    if not user:
        # Return the same shape regardless of whether the user exists to avoid enumeration.
        return {"verified": False, "role": None}

    return {
        "verified": user.email_verified,
        "role": user.role if user.email_verified else None,
    }


@router.post("/forgot-password", dependencies=[Depends(rate_limit("auth:forgot_password", limit=3, window_seconds=300))])
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Request a password-reset link.

    Always returns 200 regardless of whether the email exists — this prevents
    an attacker from discovering which emails are registered (anti-enumeration).

    Flow
    ----
    1. Look up user by email.
    2. If not found or email not verified → silent 200 (no token created).
    3. Invalidate any existing unused reset tokens for this user.
    4. Generate a new secure token, hash it, store in password_reset_tokens.
    5. Send email with the reset link (best-effort).
    """
    _SAFE_RESPONSE = {"message": "If that email is registered, a password reset link has been sent"}

    user = db.query(User).filter(User.email == payload.email).first()

    # Silent 200 for unknown / unverified emails (anti-enumeration)
    if not user or not user.email_verified:
        return _SAFE_RESPONSE

    # Invalidate all previous unused reset tokens for this user
    db.query(PasswordResetToken)\
        .filter(PasswordResetToken.user_id == user.id)\
        .filter(PasswordResetToken.used_at.is_(None))\
        .delete()

    # Generate token — store only the hash so a DB leak can't be replayed
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_refresh_token(raw_token)   # same SHA-256 helper
    expires_at = _utcnow() + timedelta(minutes=PASSWORD_RESET_EXPIRE_MINUTES)

    db.add(PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
    ))
    db.commit()

    # Email is best-effort — token is already safely in the DB
    try:
        send_password_reset_email(user.email, raw_token)
    except Exception as e:
        logger.error("Failed to send password reset email to user_id=%s: %s", user.id, e)

    return _SAFE_RESPONSE


@router.post("/reset-password", dependencies=[Depends(rate_limit("auth:reset_password", limit=5, window_seconds=300))])
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    """
    Set a new password using the token from the reset email.

    Flow
    ----
    1. Hash the incoming raw token and look it up in password_reset_tokens.
    2. Reject if not found, already used, or expired.
    3. Mark the token as used (prevents replay).
    4. Hash and save the new password.
    5. Clear the account lockout state (user proved they own the email).
    6. Revoke ALL existing refresh tokens (all sessions invalidated on pw change).
    """
    normalized_token = "".join(payload.token.split())
    token_hash = _hash_refresh_token(normalized_token)
    stored = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token_hash == token_hash)
        .first()
    )

    if not stored or stored.used_at is not None:
        raise HTTPException(400, "Invalid or already used reset token")

    if stored.expires_at < _utcnow():
        raise HTTPException(400, "Reset token has expired. Please request a new one")

    # Mark token as used immediately to block replay attacks
    stored.used_at = _utcnow()

    # Update the user's password
    user = db.get(User, stored.user_id)
    if not user:
        raise HTTPException(404, "User not found")

    user.password = hash_password(payload.new_password)

    # Clear any lockout so the user can log in right away
    _reset_lock(user)

    # Revoke all active refresh tokens — all sessions end on password change
    db.query(RefreshToken)\
        .filter(RefreshToken.user_id == user.id)\
        .filter(RefreshToken.revoked_at.is_(None))\
        .update({"revoked_at": _utcnow()})

    db.commit()

    return {"message": "Password reset successfully. Please log in with your new password"}
