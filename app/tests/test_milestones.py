"""
Milestone Endpoint Tests
------------------------
POST /milestones/{id}/upload-proof → NGO uploads proof
Run: pytest app/tests/test_milestones.py -v
"""

import pytest
import uuid
import io
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import SessionLocal
from app.core.security import hash_password, create_access_token
from app.models.user import User
from app.models.ngo import NGO
from app.models.campaign import Campaign
from app.models.milestone import Milestone
from app.models.proof import Proof

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
def ngo(db: Session):
    unique     = uuid.uuid4().hex[:8]
    email      = f"ngo_{unique}@milestones.com"
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
def regular_user(db: Session):
    unique = uuid.uuid4().hex[:8]
    user   = User(
        email          = f"user_{unique}@milestones.com",
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
def campaign_with_milestone(db: Session, ngo):
    _ngo_user, ngo_record = ngo

    campaign = Campaign(
        ngo_id=ngo_record.id, title="Camp for Milestones",
        description="Test", purpose="Test",
        image_url="https://example.com/img.jpg",
        target_amount=50000.0, raised_amount=0.0, status="active",
    )
    db.add(campaign)
    db.flush()

    milestone = Milestone(
        campaign_id=campaign.id, title="Milestone 1",
        description="First milestone", target_amount=10000.0,
        order_number=1, status="active",
    )
    db.add(milestone)
    db.commit()
    db.refresh(campaign)
    db.refresh(milestone)

    yield campaign, milestone

    try:
        db.query(Proof).filter(Proof.milestone_id == milestone.id).delete()
        db.delete(milestone)
        db.delete(campaign)
        db.commit()
    except Exception:
        db.rollback()


def fake_image_file():
    """Returns a fake file-like object for upload testing."""
    return io.BytesIO(b"fake-image-content-for-testing")


# ─────────────────────────────────────────────────────────
#  TESTS — POST /milestones/{id}/upload-proof
# ─────────────────────────────────────────────────────────

class TestUploadProof:

    def test_ngo_can_upload_proof(
        self, ngo, campaign_with_milestone, db: Session
    ):
        ngo_user, _   = ngo
        _camp, milestone = campaign_with_milestone

        res = client.post(
            f"/campaigns/{milestone.id}/upload-proof",
            files={"file": ("test.jpg", fake_image_file(), "image/jpeg")},
            headers=auth_header(ngo_user),
        )
        # 200 = success | 503 = Cloudinary not configured in test env
        assert res.status_code in (200, 503)

        if res.status_code == 200:
            # Cleanup proof created
            db.query(Proof).filter(
                Proof.milestone_id == milestone.id
            ).delete()
            db.commit()

    def test_regular_user_cannot_upload_proof(
        self, regular_user: User, campaign_with_milestone
    ):
        _camp, milestone = campaign_with_milestone
        res = client.post(
            f"/campaigns/{milestone.id}/upload-proof",
            files={"file": ("test.jpg", fake_image_file(), "image/jpeg")},
            headers=auth_header(regular_user),
        )
        assert res.status_code == 403

    def test_no_auth_returns_401(self, campaign_with_milestone):
        _camp, milestone = campaign_with_milestone
        res = client.post(
            f"/campaigns/{milestone.id}/upload-proof",
            files={"file": ("test.jpg", fake_image_file(), "image/jpeg")},
        )
        assert res.status_code == 401

    def test_nonexistent_milestone_returns_404(self, ngo):
        ngo_user, _ = ngo
        res = client.post(
            "/campaigns/999999/upload-proof",
            files={"file": ("test.jpg", fake_image_file(), "image/jpeg")},
            headers=auth_header(ngo_user),
        )
        assert res.status_code == 404

    def test_no_file_returns_422(self, ngo, campaign_with_milestone):
        ngo_user, _      = ngo
        _camp, milestone = campaign_with_milestone
        res = client.post(
            f"/campaigns/{milestone.id}/upload-proof",
            headers=auth_header(ngo_user),
        )
        assert res.status_code == 422
