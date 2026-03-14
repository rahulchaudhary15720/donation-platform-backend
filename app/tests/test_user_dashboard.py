"""
User Dashboard Integration Tests
---------------------------------
- Creates real records in the DB before each test
- Deletes ONLY those records after each test
- Never drops or modifies any table
- Run with: pytest app/tests/test_user_dashboard.py -v
"""

import pytest
import uuid
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import SessionLocal
from app.core.security import hash_password, create_access_token
from app.models.user import User
from app.models.campaign import Campaign
from app.models.milestone import Milestone
from app.models.donation import Donation
from app.models.ngo import NGO


# ─────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────

client = TestClient(app)


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def make_token(user: User) -> str:
    """Create a valid access token for a user."""
    return create_access_token({"sub": str(user.id), "role": user.role})


def auth_header(user: User) -> dict:
    return {"Authorization": f"Bearer {make_token(user)}"}


# ─────────────────────────────────────────────────────────
#  FIXTURES — create & auto-cleanup
# ─────────────────────────────────────────────────────────

@pytest.fixture()
def db():
    """Yields a real DB session, closes it after test."""
    database = SessionLocal()
    try:
        yield database
    finally:
        database.close()


@pytest.fixture()
def test_user(db: Session):
    """
    Creates a verified, active user.
    Deletes the user (and cascade-deletes their tokens) after test.
    """
    unique = uuid.uuid4().hex[:8]
    user = User(
        email          = f"testuser_{unique}@dashboard.com",
        password       = hash_password("TestPass@123"),
        role           = "user",
        full_name      = None,
        phone          = None,
        is_active      = True,
        email_verified = True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    yield user

    # ── CLEANUP ──────────────────────────────────────────
    db.expire_all()
    db.query(Donation).filter(Donation.user_id == user.id).delete(synchronize_session=False)
    db.commit()
    fresh_user = db.get(User, user.id)
    if fresh_user:
        db.delete(fresh_user)
        db.commit()


@pytest.fixture()
def test_ngo_user(db: Session):
    """
    Creates a verified NGO User + the matching NGO row that campaigns
    reference via Campaign.ngo_id → ngos.id.
    Yields the NGO ORM object so test_campaign can use ngo.id correctly.
    """
    unique = uuid.uuid4().hex[:8]
    user = User(
        email          = f"testngo_{unique}@dashboard.com",
        password       = hash_password("TestPass@123"),
        role           = "ngo",
        is_active      = True,
        email_verified = True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    ngo = NGO(
        user_id             = user.id,
        name                = f"Test NGO {unique}",
        description         = "Integration test NGO",
        registration_number = f"REG{unique}",
        address             = "123 Test Street",
        phone               = "+919876543210",
    )
    db.add(ngo)
    db.commit()
    db.refresh(ngo)

    yield ngo   # campaigns reference ngo.id (ngos.id)

    # ── CLEANUP ──────────────────────────────────────────
    # Delete NGO first (no cascade from user→ngo in ORM layer here),
    # then delete user.  Both are query-based for safety.
    db.expire_all()
    db.query(NGO).filter(NGO.id == ngo.id).delete(synchronize_session=False)
    db.commit()
    db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
    db.commit()


@pytest.fixture()
def test_campaign(db: Session, test_ngo_user: NGO):
    """Creates a real campaign owned by test_ngo_user (an NGO row)."""
    campaign = Campaign(
        ngo_id        = test_ngo_user.id,  # correctly references ngos.id
        title         = "Test Campaign for Dashboard",
        description   = "Integration test campaign",
        purpose       = "Testing",
        image_url     = "https://example.com/img.jpg",
        target_amount = 50000.0,
        raised_amount = 0.0,
        status        = "active",
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    yield campaign

    # ── CLEANUP ──────────────────────────────────────────
    # Delete donations + milestones first (no DB-level cascade on donations FK),
    # then delete the campaign.
    db.expire_all()
    db.query(Donation).filter(Donation.campaign_id == campaign.id).delete(synchronize_session=False)
    db.commit()
    db.query(Milestone).filter(Milestone.campaign_id == campaign.id).delete(synchronize_session=False)
    db.commit()
    fresh_campaign = db.get(Campaign, campaign.id)
    if fresh_campaign:
        db.delete(fresh_campaign)
        db.commit()


@pytest.fixture()
def test_milestone(db: Session, test_campaign: Campaign):
    """Creates a milestone under test_campaign."""
    milestone = Milestone(
        campaign_id   = test_campaign.id,
        title         = "Test Milestone",
        description   = "First milestone for test",
        target_amount = 10000.0,
        order_number  = 1,
        status        = "active",
    )
    db.add(milestone)
    db.commit()
    db.refresh(milestone)

    yield milestone

    # ── CLEANUP ──────────────────────────────────────────
    db.expire_all()
    db.query(Donation).filter(Donation.milestone_id == milestone.id).delete(synchronize_session=False)
    db.commit()
    fresh_milestone = db.get(Milestone, milestone.id)
    if fresh_milestone:
        db.delete(fresh_milestone)
        db.commit()


@pytest.fixture()
def test_donation(db: Session, test_user: User,
                  test_campaign: Campaign, test_milestone: Milestone):
    """Creates one real donation for test_user."""
    donation = Donation(
        campaign_id    = test_campaign.id,
        milestone_id   = test_milestone.id,
        user_id        = test_user.id,
        transaction_id = f"TXN-TEST-{uuid.uuid4().hex[:10].upper()}",
        amount         = 500.0,
        is_anonymous   = False,
        created_at     = utcnow(),
    )
    db.add(donation)
    db.commit()
    db.refresh(donation)

    yield donation

    # ── CLEANUP ──────────────────────────────────────────
    db.expire_all()
    fresh_donation = db.get(Donation, donation.id)
    if fresh_donation:
        db.delete(fresh_donation)
        db.commit()


# ─────────────────────────────────────────────────────────
#  TEST 1 — GET /users/me
# ─────────────────────────────────────────────────────────

class TestGetProfile:

    def test_returns_profile(self, test_user: User):
        res = client.get("/users/me", headers=auth_header(test_user))
        assert res.status_code == 200
        data = res.json()
        assert data["email"]          == test_user.email
        assert data["role"]           == "user"
        assert data["is_active"]      == True
        assert data["email_verified"] == True
        assert data["full_name"]      is None
        assert data["phone"]          is None

    def test_no_token_returns_401(self):
        res = client.get("/users/me")
        assert res.status_code == 401

    def test_fake_token_returns_401(self):
        res = client.get("/users/me",
                         headers={"Authorization": "Bearer faketoken123"})
        assert res.status_code == 401


# ─────────────────────────────────────────────────────────
#  TEST 2 — PUT /users/me
# ─────────────────────────────────────────────────────────

class TestUpdateProfile:

    def test_update_full_name(self, test_user: User):
        res = client.put("/users/me",
                         json={"full_name": "Raj Patel"},
                         headers=auth_header(test_user))
        assert res.status_code == 200
        assert res.json()["full_name"] == "Raj Patel"

    def test_update_phone(self, test_user: User):
        res = client.put("/users/me",
                         json={"phone": "+919876543210"},
                         headers=auth_header(test_user))
        assert res.status_code == 200
        assert res.json()["phone"] == "+919876543210"

    def test_update_both(self, test_user: User):
        res = client.put("/users/me",
                         json={"full_name": "Test User", "phone": "+11234567890"},
                         headers=auth_header(test_user))
        assert res.status_code == 200
        assert res.json()["full_name"] == "Test User"
        assert res.json()["phone"]     == "+11234567890"

    def test_empty_body_returns_422(self, test_user: User):
        res = client.put("/users/me",
                         json={},
                         headers=auth_header(test_user))
        assert res.status_code == 422

    def test_full_name_too_short_returns_422(self, test_user: User):
        res = client.put("/users/me",
                         json={"full_name": "A"},
                         headers=auth_header(test_user))
        assert res.status_code == 422

    def test_invalid_phone_returns_422(self, test_user: User):
        res = client.put("/users/me",
                         json={"phone": "abc"},
                         headers=auth_header(test_user))
        assert res.status_code == 422


# ─────────────────────────────────────────────────────────
#  TEST 3 — PUT /users/me/password
# ─────────────────────────────────────────────────────────

class TestChangePassword:

    def test_wrong_current_password(self, test_user: User):
        res = client.put("/users/me/password",
                         json={"current_password": "WrongPass@999",
                               "new_password":     "NewPass@456"},
                         headers=auth_header(test_user))
        assert res.status_code == 400
        assert "incorrect" in res.json()["detail"].lower()

    def test_same_password_rejected(self, test_user: User):
        res = client.put("/users/me/password",
                         json={"current_password": "TestPass@123",
                               "new_password":     "TestPass@123"},
                         headers=auth_header(test_user))
        assert res.status_code == 400
        assert "different" in res.json()["detail"].lower()

    def test_weak_new_password_rejected(self, test_user: User):
        res = client.put("/users/me/password",
                         json={"current_password": "TestPass@123",
                               "new_password":     "weak"},
                         headers=auth_header(test_user))
        assert res.status_code == 422

    def test_successful_password_change(self, test_user: User, db: Session):
        res = client.put("/users/me/password",
                         json={"current_password": "TestPass@123",
                               "new_password":     "Changed@789"},
                         headers=auth_header(test_user))
        assert res.status_code == 200
        assert "changed successfully" in res.json()["message"].lower()

        # Reset back so other tests still work with TestPass@123
        db.refresh(test_user)
        test_user.password = hash_password("TestPass@123")
        db.commit()


# ─────────────────────────────────────────────────────────
#  TEST 4 — GET /users/me/stats
# ─────────────────────────────────────────────────────────

class TestDonationStats:

    def test_stats_zero_when_no_donations(self, test_user: User):
        res = client.get("/users/me/stats", headers=auth_header(test_user))
        assert res.status_code == 200
        data = res.json()
        assert data["total_donated"]       == 0.0
        assert data["total_donations"]     == 0
        assert data["campaigns_supported"] == 0
        assert data["this_month_donated"]  == 0.0
        assert data["first_donation_date"] is None

    def test_stats_correct_after_donation(
        self, test_user: User, test_donation: Donation
    ):
        res = client.get("/users/me/stats", headers=auth_header(test_user))
        assert res.status_code == 200
        data = res.json()
        assert data["total_donated"]       == 500.0
        assert data["total_donations"]     == 1
        assert data["campaigns_supported"] == 1
        assert data["first_donation_date"] is not None


# ─────────────────────────────────────────────────────────
#  TEST 5 — GET /users/me/donations
# ─────────────────────────────────────────────────────────

class TestDonationHistory:

    def test_empty_list_when_no_donations(self, test_user: User):
        res = client.get("/users/me/donations", headers=auth_header(test_user))
        assert res.status_code == 200
        data = res.json()
        assert data["data"]        == []
        assert data["total_count"] == 0
        assert data["has_more"]    == False

    def test_donation_appears_in_list(
        self, test_user: User, test_donation: Donation
    ):
        res = client.get("/users/me/donations", headers=auth_header(test_user))
        assert res.status_code == 200
        data = res.json()
        assert data["total_count"] == 1
        assert data["data"][0]["transaction_id"] == test_donation.transaction_id
        assert data["data"][0]["amount"]         == 500.0
        assert data["data"][0]["campaign"]       is not None

    def test_pagination_works(self, test_user: User, test_donation: Donation):
        res = client.get("/users/me/donations?page=1&limit=5",
                         headers=auth_header(test_user))
        assert res.status_code == 200
        data = res.json()
        assert data["page"]        == 1
        assert data["limit"]       == 5
        assert data["total_pages"] == 1

    def test_invalid_sort_order(self, test_user: User):
        res = client.get("/users/me/donations?sort_order=xyz",
                         headers=auth_header(test_user))
        assert res.status_code == 422

    def test_limit_capped_at_50(self, test_user: User):
        res = client.get("/users/me/donations?limit=9999",
                         headers=auth_header(test_user))
        assert res.status_code == 200
        assert res.json()["limit"] == 50

    def test_filter_by_campaign_id(
        self, test_user: User, test_donation: Donation, test_campaign: Campaign
    ):
        res = client.get(f"/users/me/donations?campaign_id={test_campaign.id}",
                         headers=auth_header(test_user))
        assert res.status_code == 200
        assert res.json()["total_count"] == 1

    def test_filter_nonexistent_campaign(self, test_user: User):
        res = client.get("/users/me/donations?campaign_id=999999",
                         headers=auth_header(test_user))
        assert res.status_code == 200
        assert res.json()["total_count"] == 0


# ─────────────────────────────────────────────────────────
#  TEST 6 — GET /users/me/donations/{id}
# ─────────────────────────────────────────────────────────

class TestSingleDonation:

    def test_get_own_donation(
        self, test_user: User, test_donation: Donation
    ):
        res = client.get(f"/users/me/donations/{test_donation.id}",
                         headers=auth_header(test_user))
        assert res.status_code == 200
        data = res.json()
        assert data["id"]             == test_donation.id
        assert data["transaction_id"] == test_donation.transaction_id
        assert data["amount"]         == 500.0

    def test_other_user_donation_returns_404(
        self, test_user: User, test_donation: Donation, db: Session
    ):
        """A different user trying to access someone else's donation gets 404."""
        other = User(
            email          = f"other_{uuid.uuid4().hex[:6]}@test.com",
            password       = hash_password("TestPass@123"),
            role           = "user",
            is_active      = True,
            email_verified = True,
        )
        db.add(other)
        db.commit()
        db.refresh(other)

        res = client.get(f"/users/me/donations/{test_donation.id}",
                         headers=auth_header(other))
        assert res.status_code == 404

        # Cleanup other user
        db.delete(other)
        db.commit()

    def test_nonexistent_donation_returns_404(self, test_user: User):
        res = client.get("/users/me/donations/999999",
                         headers=auth_header(test_user))
        assert res.status_code == 404
