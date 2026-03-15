from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer , HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.user import User

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = HTTPBearer()
oauth2_scheme_optional = HTTPBearer(auto_error=False)



def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(password: str, hashed: str):
    return pwd_context.verify(password, hashed)

def create_access_token(data: dict, expires_minutes: int | None = None):
    to_encode = data.copy()
    minutes = (
        expires_minutes
        if expires_minutes is not None
        else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    # Use timezone-aware UTC time to derive the value, but strip tzinfo before
    # encoding — python-jose serialises datetime objects and some versions have
    # inconsistent handling of aware vs naive datetimes.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expire = now + timedelta(minutes=minutes)
    to_encode.setdefault("type", "access")
    to_encode.update({"iat": int(now.timestamp()), "exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme),  # ← changed
    db: Session = Depends(get_db)
):
    token = credentials.credentials   # ← ADD this one line to extract token string

    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        token_type = payload.get("type")
        if token_type and token_type != "access":
            raise HTTPException(status_code=401)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401)
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=401)
    except JWTError:
        raise HTTPException(status_code=401)

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401)
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account not activated")
    if not user.email_verified:
        raise HTTPException(status_code=403, detail="Email not verified")
    return user


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db),
):
    if not credentials:
        return None

    token = credentials.credentials

    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        token_type = payload.get("type")
        if token_type and token_type != "access":
            return None
        user_id = payload.get("sub")
        if not user_id:
            return None
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return None
    except JWTError:
        return None

    user = db.get(User, user_id)
    if not user or not user.is_active or not user.email_verified:
        return None

    return user
