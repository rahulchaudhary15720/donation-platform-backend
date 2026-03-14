"""
NGO Endpoint Tests
------------------
GET /ngos/me → NGO profile
Run: pytest app/tests/test_ngos.py -v
"""

import pytest
import uuid
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import SessionLocal
from app.core.security import hash_password, create_access_token
from app.models.user import User
from app.models.ngo import NGO

client = TestClient(app)


def auth_header(user: User) -> dict:
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return {"Authorization": f"Bearer {token}"}


# ─────────────────────────────────────────────────────────
#  FIXTURES
# ─────────────────────────────────────────────────────────

@pytest.fixture()
def db():
    database = SessionLocal()
    try:
        yield database
    finally:
        database.close()


@pytest.fixture()
def active_ngo(db: Session):
    """Approved NGO — is_active=True."""
    unique     = uuid.uuid4().hex[:8]
    email      = f"ngo_{unique}@ngos.com"
    pwd        = hash_password("TestPass@123")

    ngo_user   = User(
        email=email, password=pwd, role="ngo",
        is_active=True, email_verified=True,
    )
    db.add(ngo_user)
    db.flush()

    ngo_record = NGO(
        user_id             = ngo_user.id,
        name                = f"Test NGO {unique}",
        description         = "Integration test NGO",
        registration_number = f"REG{unique}",
        address             = "123 Test Street",
        phone               = "+919876543210",
    )
    db.add(ngo_record)
    db.commit()
    db.refresh(ngo_user)
    db.refresh(ngo_record)

    yield ngo_user, ngo_record

    try:
        db.expire_all()
        db.query(NGO).filter(NGO.id == ngo_record.id).delete(synchronize_session=False)
        db.commit()
        db.query(User).filter(User.id == ngo_user.id).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()


@pytest.fixture()
def pending_ngo(db: Session):
    """Pending NGO — is_active=False, not yet approved."""
    unique   = uuid.uuid4().hex[:8]
    email    = f"pending_{unique}@ngos.com"
    pwd      = hash_password("TestPass@123")

    ngo_user = User(
        email=email, password=pwd, role="ngo",
        is_active=False,         # ← pending approval
        email_verified=True,
    )
    db.add(ngo_user)
    db.commit()
    db.refresh(ngo_user)

    yield ngo_user

    try:
        db.delete(ngo_user)
        db.commit()
    except Exception:
        db.rollback()


@pytest.fixture()
def regular_user(db: Session):
    unique = uuid.uuid4().hex[:8]
    user   = User(
        email=f"user_{unique}@ngos.com",
        password=hash_password("TestPass@123"),
        role="user", is_active=True, email_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    yield user

    try:
        db.delete(user)
        db.commit()
    except Exception:
        db.rollback()


# ─────────────────────────────────────────────────────────
#  TESTS — GET /ngos/me
# ─────────────────────────────────────────────────────────

class TestNgoMe:

    def test_active_ngo_gets_profile(self, active_ngo):
        ngo_user, _ = active_ngo
        res = client.get("/ngos/me", headers=auth_header(ngo_user))
        assert res.status_code == 200
        assert res.json()["email"] == ngo_user.email
        assert res.json()["role"]  == "ngo"

    def test_pending_ngo_is_blocked(self, pending_ngo: User):
        """Pending NGO (is_active=False) must be blocked — ngorequired checks is_active."""
        res = client.get("/ngos/me", headers=auth_header(pending_ngo))
        assert res.status_code == 403

    def test_regular_user_is_blocked(self, regular_user: User):
        res = client.get("/ngos/me", headers=auth_header(regular_user))
        assert res.status_code == 403

    def test_no_token_returns_401(self):
        res = client.get("/ngos/me")
        assert res.status_code == 401

    def test_fake_token_returns_401(self):
        res = client.get("/ngos/me",
                         headers={"Authorization": "Bearer faketoken"})
        assert res.status_code == 401
