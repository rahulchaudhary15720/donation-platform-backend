"""
Campaign Endpoint Tests
-----------------------
POST /campaigns  → NGO creates campaign
GET  /campaigns  → Public lists active campaigns
Run: pytest app/tests/test_campaigns.py -v
"""

import io
import pytest
import uuid
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import SessionLocal
from app.core.security import hash_password, create_access_token
from app.models.user import User
from app.models.ngo import NGO
from app.models.campaign import Campaign

client = TestClient(app)


# ─────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────

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
def ngo(db: Session):
    """Creates User (role=ngo) + Ngo record. Yields (ngo_user, ngo_record)."""
    unique    = uuid.uuid4().hex[:8]
    email     = f"ngo_{unique}@campaigns.com"
    pwd       = hash_password("TestPass@123")

    ngo_user  = User(
        email          = email,
        password       = pwd,
        role           = "ngo",
        is_active      = True,
        email_verified = True,
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
        db.query(Campaign).filter(Campaign.ngo_id == ngo_record.id).delete(synchronize_session=False)
        db.commit()
        db.query(NGO).filter(NGO.id == ngo_record.id).delete(synchronize_session=False)
        db.commit()
        db.query(User).filter(User.id == ngo_user.id).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()


@pytest.fixture()
def regular_user(db: Session):
    """A plain user — should NOT be able to create campaigns."""
    unique = uuid.uuid4().hex[:8]
    user   = User(
        email          = f"user_{unique}@campaigns.com",
        password       = hash_password("TestPass@123"),
        role           = "user",
        is_active      = True,
        email_verified = True,
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


@pytest.fixture()
def test_campaign(db: Session, ngo):
    """Creates one campaign for the test NGO."""
    _ngo_user, ngo_record = ngo
    campaign = Campaign(
        ngo_id        = ngo_record.id,
        title         = f"Camp_{uuid.uuid4().hex[:6]}",
        description   = "Test description",
        purpose       = "Test purpose",
        image_url     = "https://example.com/img.jpg",
        target_amount = 100000.0,
        raised_amount = 0.0,
        status        = "active",
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    yield campaign

    try:
        db.delete(campaign)
        db.commit()
    except Exception:
        db.rollback()


# ─────────────────────────────────────────────────────────
#  TEST 1 — GET /campaigns (public)
# ─────────────────────────────────────────────────────────

class TestListCampaigns:

    def test_public_access_no_auth_needed(self):
        res = client.get("/campaigns")
        assert res.status_code == 200

    def test_returns_list(self):
        res = client.get("/campaigns")
        assert isinstance(res.json(), list)

    def test_created_campaign_appears_in_list(
        self, test_campaign: Campaign
    ):
        res   = client.get("/campaigns")
        ids   = [c["id"] for c in res.json()]
        assert test_campaign.id in ids

    def test_inactive_campaign_not_listed(self, db: Session, ngo):
        _ngo_user, ngo_record = ngo
        draft = Campaign(
            ngo_id        = ngo_record.id,
            title         = "Draft Campaign",
            description   = "Should not appear",
            purpose       = "Hidden",
            image_url     = "https://example.com/img.jpg",
            target_amount = 5000.0,
            raised_amount = 0.0,
            status        = "draft",     # ← NOT active
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)

        res = client.get("/campaigns")
        ids = [c["id"] for c in res.json()]
        assert draft.id not in ids

        db.delete(draft)
        db.commit()


# ─────────────────────────────────────────────────────────
#  TEST 2 — POST /campaigns (NGO only)
# ─────────────────────────────────────────────────────────

class TestCreateCampaign:

    def test_ngo_can_create_campaign(self, ngo, db: Session):
        ngo_user, _ngo_record = ngo
        res = client.post(
            "/campaigns/campaign",
            params={
                "title":         "New Campaign",
                "description":   "Test description",
                "purpose":       "Test purpose",
                "target_amount": 50000,
            },
            files={"file": ("test.jpg", io.BytesIO(b"fake-image"), "image/jpeg")},
            headers=auth_header(ngo_user),
        )
        # 200 = success | 503 = Cloudinary not configured in test env
        assert res.status_code in (200, 503)
        if res.status_code == 200:
            data = res.json()
            assert "campaign_id" in data
            # Cleanup created campaign
            db.query(Campaign).filter(Campaign.id == data["campaign_id"]).delete(synchronize_session=False)
            db.commit()

    def test_regular_user_cannot_create_campaign(self, regular_user: User):
        res = client.post(
            "/campaigns/campaign",
            params={"title": "Hack Camp", "target_amount": 1000},
            headers=auth_header(regular_user),
        )
        assert res.status_code == 403

    def test_no_auth_returns_401(self):
        res = client.post(
            "/campaigns/campaign",
            params={"title": "No Auth", "target_amount": 1000},
        )
        assert res.status_code == 401

    def test_missing_title_returns_422(self, ngo):
        ngo_user, _ = ngo
        res = client.post(
            "/campaigns/campaign",
            params={"target_amount": 1000},
            files={"file": ("test.jpg", io.BytesIO(b"fake"), "image/jpeg")},
            headers=auth_header(ngo_user),
        )
        assert res.status_code == 422

    def test_missing_target_amount_returns_422(self, ngo):
        ngo_user, _ = ngo
        res = client.post(
            "/campaigns/campaign",
            params={"title": "Missing Amount"},
            files={"file": ("test.jpg", io.BytesIO(b"fake"), "image/jpeg")},
            headers=auth_header(ngo_user),
        )
        assert res.status_code == 422
