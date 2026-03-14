"""
Payment Endpoint Tests
----------------------
POST /payments/initiate     → Create a pending payment order
POST /payments/verify       → Verify signature + create Donation
GET  /payments/order/{id}   → Check order status

Uses SQLite in-memory — NO Supabase / network required.
The database is created fresh for every single test and discarded after.

Run all:   pytest app/tests/test_payments.py -v
Run one:   pytest app/tests/test_payments.py::TestInitiate::test_happy_path -v
"""

import hashlib
import hmac
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.base import Base
from app.core.security import get_db, hash_password, create_access_token
from app.core.config import settings

# ── Import ALL models so Base.metadata knows about every table ──────────────
from app.models.user import User
from app.models.ngo import NGO
from app.models.campaign import Campaign
from app.models.milestone import Milestone
from app.models.donation import Donation
from app.models.proof import Proof
from app.models.refresh_token import RefreshToken
from app.models.email_verification import EmailVerification
from app.models.email_notification import EmailNotification
from app.models.password_reset import PasswordResetToken
from app.models.payment_order import PaymentOrder

client = TestClient(app)


# ─────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────

def auth_header(user: User) -> dict:
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return {"Authorization": f"Bearer {token}"}


def compute_signature(order_id: str, payment_id: str) -> str:
    """Replicate the exact same HMAC used in payments.py — used in tests to forge valid signatures."""
    message = f"{order_id}|{payment_id}".encode()
    key     = settings.JWT_SECRET.encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


# ─────────────────────────────────────────────────────────
#  DATABASE FIXTURES — SQLite in-memory, no Supabase needed
# ─────────────────────────────────────────────────────────

@pytest.fixture()
def memory_engine():
    """
    Creates a completely fresh SQLite in-memory database for every test.
    All tables are created from the SQLAlchemy models.
    Dropped automatically when the test ends — zero cleanup needed.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,   # single connection shared across threads → same in-memory DB
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def db(memory_engine):
    """
    Yields a SQLAlchemy Session backed by SQLite.
    Also overrides FastAPI's get_db dependency so that the test client
    and fixtures share the SAME session — what the API writes is visible
    to the fixture assertions immediately.
    """
    TestSession = sessionmaker(bind=memory_engine, autoflush=False)
    session = TestSession()

    # Make every API call in this test use the SQLite session
    app.dependency_overrides[get_db] = lambda: session

    yield session

    session.close()
    # Restore so other test files are not affected
    app.dependency_overrides.pop(get_db, None)


# ─────────────────────────────────────────────────────────
#  DOMAIN FIXTURES
# ─────────────────────────────────────────────────────────

@pytest.fixture()
def donor(db: Session):
    """A normal donor user."""
    unique = uuid.uuid4().hex[:8]
    user   = User(
        email          = f"donor_{unique}@payments.com",
        password       = hash_password("TestPass@123"),
        role           = "user",
        is_active      = True,
        email_verified = True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user                  # no teardown needed — whole DB drops after test


@pytest.fixture()
def another_donor(db: Session):
    """A second user — used to test cross-user access is blocked."""
    unique = uuid.uuid4().hex[:8]
    user   = User(
        email          = f"donor2_{unique}@payments.com",
        password       = hash_password("TestPass@123"),
        role           = "user",
        is_active      = True,
        email_verified = True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def ngo_with_campaign(db: Session):
    """
    Creates a complete NGO → Campaign → 3 Milestones stack.
    Yields (ngo_user, ngo_record, campaign, active_milestone).
    """
    unique = uuid.uuid4().hex[:8]

    ngo_user = User(
        email          = f"ngo_{unique}@payments.com",
        password       = hash_password("TestPass@123"),
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
    db.flush()

    campaign = Campaign(
        ngo_id        = ngo_record.id,
        title         = f"Campaign {unique}",
        description   = "Test campaign description",
        purpose       = "Integration testing",
        image_url     = "https://example.com/campaign.jpg",
        target_amount = 100_000.0,
        raised_amount = 0.0,
        status        = "active",
    )
    db.add(campaign)
    db.flush()

    ms1 = Milestone(                          # active — accepts donations
        campaign_id=campaign.id, title="Phase 1: Foundation",
        description="First milestone", target_amount=30_000.0,
        order_number=1, status="active",
    )
    ms2 = Milestone(                          # locked — must reject donations
        campaign_id=campaign.id, title="Phase 2: Construction",
        description="Second milestone", target_amount=40_000.0,
        order_number=2, status="locked",
    )
    ms3 = Milestone(                          # locked
        campaign_id=campaign.id, title="Phase 3: Completion",
        description="Third milestone", target_amount=30_000.0,
        order_number=3, status="locked",
    )
    db.add_all([ms1, ms2, ms3])
    db.commit()
    db.refresh(ms1)
    db.refresh(campaign)

    return ngo_user, ngo_record, campaign, ms1


# ─────────────────────────────────────────────────────────
#  TESTS — POST /payments/initiate
# ─────────────────────────────────────────────────────────

class TestInitiate:

    def test_happy_path(self, donor: User, ngo_with_campaign):
        """Valid user + active campaign + active milestone → 200."""
        _, _, campaign, milestone = ngo_with_campaign

        res = client.post(
            "/payments/initiate",
            json={
                "campaign_id":  campaign.id,
                "milestone_id": milestone.id,
                "amount":       500.0,
                "is_anonymous": False,
            },
            headers=auth_header(donor),
        )
        assert res.status_code == 200, res.text

        body = res.json()
        assert body["order_id"].startswith("MOCK_ORDER_")
        assert body["mock_payment_id"].startswith("MOCK_PAY_")
        assert len(body["mock_signature"]) == 64        # SHA-256 hex digest
        assert body["amount"]  == 500.0
        assert body["gateway"] == "mock"
        assert body["currency"] == "INR"
        assert "description" in body

    def test_order_saved_in_db(self, donor: User, ngo_with_campaign, db: Session):
        """After initiate, a PaymentOrder row must exist in the DB with status=pending."""
        _, _, campaign, milestone = ngo_with_campaign

        res = client.post(
            "/payments/initiate",
            json={
                "campaign_id":  campaign.id,
                "milestone_id": milestone.id,
                "amount":       250.0,
                "is_anonymous": False,
            },
            headers=auth_header(donor),
        )
        assert res.status_code == 200

        order_id = res.json()["order_id"]
        db.expire_all()
        order = db.query(PaymentOrder).filter(PaymentOrder.order_id == order_id).first()

        assert order is not None
        assert order.status   == "pending"
        assert order.amount   == 250.0
        assert order.user_id  == donor.id
        assert order.gateway  == "mock"

    def test_anonymous_donation_without_email(self, donor: User, ngo_with_campaign):
        """Anonymous donor without email is allowed."""
        _, _, campaign, milestone = ngo_with_campaign

        res = client.post(
            "/payments/initiate",
            json={
                "campaign_id":  campaign.id,
                "milestone_id": milestone.id,
                "amount":       100.0,
                "is_anonymous": True,
            },
            headers=auth_header(donor),
        )
        assert res.status_code == 200
        assert res.json()["order_id"].startswith("MOCK_ORDER_")

    def test_anonymous_donation_with_email(self, donor: User, ngo_with_campaign):
        """Anonymous donor WITH email — email is encrypted and stored."""
        _, _, campaign, milestone = ngo_with_campaign

        res = client.post(
            "/payments/initiate",
            json={
                "campaign_id":  campaign.id,
                "milestone_id": milestone.id,
                "amount":       100.0,
                "is_anonymous": True,
                "email":        "anon@donor.com",
            },
            headers=auth_header(donor),
        )
        assert res.status_code == 200

    def test_no_auth_returns_401(self, ngo_with_campaign):
        """Unauthenticated request must be rejected."""
        _, _, campaign, milestone = ngo_with_campaign

        res = client.post(
            "/payments/initiate",
            json={
                "campaign_id":  campaign.id,
                "milestone_id": milestone.id,
                "amount":       100.0,
                "is_anonymous": False,
            },
        )
        assert res.status_code == 401

    def test_inactive_campaign_returns_404(self, donor: User, ngo_with_campaign, db: Session):
        """Draft/paused campaigns are not valid targets."""
        _, _, campaign, milestone = ngo_with_campaign

        # Temporarily deactivate campaign
        campaign.status = "draft"
        db.commit()

        res = client.post(
            "/payments/initiate",
            json={
                "campaign_id":  campaign.id,
                "milestone_id": milestone.id,
                "amount":       100.0,
                "is_anonymous": False,
            },
            headers=auth_header(donor),
        )
        assert res.status_code == 404

        # Restore
        campaign.status = "active"
        db.commit()

    def test_locked_milestone_returns_400(self, donor: User, ngo_with_campaign, db: Session):
        """Locked milestones must NOT accept donations."""
        _, _, campaign, _ = ngo_with_campaign

        locked_ms = (
            db.query(Milestone)
            .filter(Milestone.campaign_id == campaign.id, Milestone.status == "locked")
            .first()
        )
        assert locked_ms is not None, "Test setup error: no locked milestone found"

        res = client.post(
            "/payments/initiate",
            json={
                "campaign_id":  campaign.id,
                "milestone_id": locked_ms.id,
                "amount":       100.0,
                "is_anonymous": False,
            },
            headers=auth_header(donor),
        )
        assert res.status_code == 400
        assert "locked" in res.json()["detail"].lower()

    def test_wrong_milestone_for_campaign_returns_404(self, donor: User, ngo_with_campaign, db: Session):
        """Milestone ID that doesn't belong to the campaign → 404."""
        _, _, campaign, _ = ngo_with_campaign

        res = client.post(
            "/payments/initiate",
            json={
                "campaign_id":  campaign.id,
                "milestone_id": 999999,       # non-existent
                "amount":       100.0,
                "is_anonymous": False,
            },
            headers=auth_header(donor),
        )
        assert res.status_code == 404

    def test_zero_amount_returns_422(self, donor: User, ngo_with_campaign):
        """Amount must be > 0."""
        _, _, campaign, milestone = ngo_with_campaign

        res = client.post(
            "/payments/initiate",
            json={
                "campaign_id":  campaign.id,
                "milestone_id": milestone.id,
                "amount":       0,
                "is_anonymous": False,
            },
            headers=auth_header(donor),
        )
        assert res.status_code == 422

    def test_negative_amount_returns_422(self, donor: User, ngo_with_campaign):
        """Negative amounts must be rejected by Pydantic."""
        _, _, campaign, milestone = ngo_with_campaign

        res = client.post(
            "/payments/initiate",
            json={
                "campaign_id":  campaign.id,
                "milestone_id": milestone.id,
                "amount":       -100,
                "is_anonymous": False,
            },
            headers=auth_header(donor),
        )
        assert res.status_code == 422

    def test_amount_exceeds_max_returns_422(self, donor: User, ngo_with_campaign):
        """Amount > ₹10,00,000 must be rejected."""
        _, _, campaign, milestone = ngo_with_campaign

        res = client.post(
            "/payments/initiate",
            json={
                "campaign_id":  campaign.id,
                "milestone_id": milestone.id,
                "amount":       1_000_001,
                "is_anonymous": False,
            },
            headers=auth_header(donor),
        )
        assert res.status_code == 422

    def test_invalid_email_returns_422(self, donor: User, ngo_with_campaign):
        """Malformed anonymous email must be rejected."""
        _, _, campaign, milestone = ngo_with_campaign

        res = client.post(
            "/payments/initiate",
            json={
                "campaign_id":  campaign.id,
                "milestone_id": milestone.id,
                "amount":       100.0,
                "is_anonymous": True,
                "email":        "not-an-email",
            },
            headers=auth_header(donor),
        )
        assert res.status_code == 422


# ─────────────────────────────────────────────────────────
#  TESTS — POST /payments/verify
# ─────────────────────────────────────────────────────────

class TestVerify:

    def _initiate(self, donor, campaign, milestone) -> dict:
        """Helper: initiate a payment and return the full response body."""
        res = client.post(
            "/payments/initiate",
            json={
                "campaign_id":  campaign.id,
                "milestone_id": milestone.id,
                "amount":       500.0,
                "is_anonymous": False,
            },
            headers=auth_header(donor),
        )
        assert res.status_code == 200, f"Initiate failed: {res.text}"
        return res.json()

    def test_happy_path(self, donor: User, ngo_with_campaign):
        """Full initiate → verify cycle must return a transaction_id."""
        _, _, campaign, milestone = ngo_with_campaign

        order = self._initiate(donor, campaign, milestone)

        res = client.post(
            "/payments/verify",
            json={
                "order_id":   order["order_id"],
                "payment_id": order["mock_payment_id"],
                "signature":  order["mock_signature"],
            },
            headers=auth_header(donor),
        )
        assert res.status_code == 200, res.text

        body = res.json()
        assert body["transaction_id"].startswith("TXN-")
        assert body["amount"]   == 500.0
        assert body["campaign"] == campaign.title
        assert "milestone" in body

    def test_donation_created_in_db(self, donor: User, ngo_with_campaign, db: Session):
        """After verify, a Donation row must exist in the DB."""
        _, _, campaign, milestone = ngo_with_campaign

        order = self._initiate(donor, campaign, milestone)
        res   = client.post(
            "/payments/verify",
            json={
                "order_id":   order["order_id"],
                "payment_id": order["mock_payment_id"],
                "signature":  order["mock_signature"],
            },
            headers=auth_header(donor),
        )
        assert res.status_code == 200

        txn = res.json()["transaction_id"]
        db.expire_all()
        donation = db.query(Donation).filter(Donation.transaction_id == txn).first()

        assert donation is not None
        assert donation.amount      == 500.0
        assert donation.campaign_id == campaign.id
        assert donation.user_id     == donor.id

    def test_raised_amount_incremented(self, donor: User, ngo_with_campaign, db: Session):
        """campaign.raised_amount must increase by the donated amount."""
        _, _, campaign, milestone = ngo_with_campaign

        before = campaign.raised_amount

        order = self._initiate(donor, campaign, milestone)
        res   = client.post(
            "/payments/verify",
            json={
                "order_id":   order["order_id"],
                "payment_id": order["mock_payment_id"],
                "signature":  order["mock_signature"],
            },
            headers=auth_header(donor),
        )
        assert res.status_code == 200

        db.expire_all()
        db.refresh(campaign)
        assert campaign.raised_amount == before + 500.0

    def test_order_marked_paid(self, donor: User, ngo_with_campaign, db: Session):
        """PaymentOrder.status must be 'paid' after successful verify."""
        _, _, campaign, milestone = ngo_with_campaign

        order = self._initiate(donor, campaign, milestone)
        client.post(
            "/payments/verify",
            json={
                "order_id":   order["order_id"],
                "payment_id": order["mock_payment_id"],
                "signature":  order["mock_signature"],
            },
            headers=auth_header(donor),
        )

        db.expire_all()
        db_order = db.query(PaymentOrder).filter(
            PaymentOrder.order_id == order["order_id"]
        ).first()
        assert db_order.status == "paid"

    def test_double_verify_returns_400(self, donor: User, ngo_with_campaign):
        """Calling verify twice on the same order_id must fail with 400."""
        _, _, campaign, milestone = ngo_with_campaign

        order = self._initiate(donor, campaign, milestone)
        verify_body = {
            "order_id":   order["order_id"],
            "payment_id": order["mock_payment_id"],
            "signature":  order["mock_signature"],
        }

        res1 = client.post("/payments/verify", json=verify_body, headers=auth_header(donor))
        assert res1.status_code == 200

        res2 = client.post("/payments/verify", json=verify_body, headers=auth_header(donor))
        assert res2.status_code == 400
        assert "already verified" in res2.json()["detail"].lower()

    def test_wrong_signature_returns_400(self, donor: User, ngo_with_campaign):
        """Tampered signature must be rejected."""
        _, _, campaign, milestone = ngo_with_campaign

        order = self._initiate(donor, campaign, milestone)

        res = client.post(
            "/payments/verify",
            json={
                "order_id":   order["order_id"],
                "payment_id": order["mock_payment_id"],
                "signature":  "a" * 64,    # garbage signature
            },
            headers=auth_header(donor),
        )
        assert res.status_code == 400
        assert "signature" in res.json()["detail"].lower()

    def test_wrong_payment_id_returns_400(self, donor: User, ngo_with_campaign):
        """Mismatched payment_id must be rejected even if signature looks valid for it."""
        _, _, campaign, milestone = ngo_with_campaign

        order = self._initiate(donor, campaign, milestone)

        # Use a different payment_id — signature will also be wrong
        fake_pay_id = "MOCK_PAY_FFFFFFFF0000"
        fake_sig    = compute_signature(order["order_id"], fake_pay_id)

        res = client.post(
            "/payments/verify",
            json={
                "order_id":   order["order_id"],
                "payment_id": fake_pay_id,
                "signature":  fake_sig,
            },
            headers=auth_header(donor),
        )
        # Either signature fails (400) or payment_id mismatch (400)
        assert res.status_code == 400

    def test_order_not_found_returns_404(self, donor: User):
        """Non-existent order_id must return 404."""
        res = client.post(
            "/payments/verify",
            json={
                "order_id":   "MOCK_ORDER_DOESNOTEXIST",
                "payment_id": "MOCK_PAY_DOESNOTEXIST",
                "signature":  compute_signature("MOCK_ORDER_DOESNOTEXIST", "MOCK_PAY_DOESNOTEXIST"),
            },
            headers=auth_header(donor),
        )
        assert res.status_code == 404

    def test_no_auth_returns_401(self, donor: User, ngo_with_campaign):
        """Verify without token must return 401."""
        _, _, campaign, milestone = ngo_with_campaign

        order = self._initiate(donor, campaign, milestone)

        res = client.post(
            "/payments/verify",
            json={
                "order_id":   order["order_id"],
                "payment_id": order["mock_payment_id"],
                "signature":  order["mock_signature"],
            },
        )
        assert res.status_code == 401


# ─────────────────────────────────────────────────────────
#  TESTS — GET /payments/order/{order_id}
# ─────────────────────────────────────────────────────────

class TestOrderStatus:

    def test_pending_order_status(self, donor: User, ngo_with_campaign):
        """Freshly initiated order must show status=pending."""
        _, _, campaign, milestone = ngo_with_campaign

        res_init = client.post(
            "/payments/initiate",
            json={
                "campaign_id":  campaign.id,
                "milestone_id": milestone.id,
                "amount":       100.0,
                "is_anonymous": False,
            },
            headers=auth_header(donor),
        )
        order_id = res_init.json()["order_id"]

        res = client.get(
            f"/payments/order/{order_id}",
            headers=auth_header(donor),
        )
        assert res.status_code == 200
        assert res.json()["status"]         == "pending"
        assert res.json()["transaction_id"] is None

    def test_paid_order_shows_transaction_id(self, donor: User, ngo_with_campaign):
        """A paid order must return status=paid and the transaction_id."""
        _, _, campaign, milestone = ngo_with_campaign

        init = client.post(
            "/payments/initiate",
            json={
                "campaign_id":  campaign.id,
                "milestone_id": milestone.id,
                "amount":       100.0,
                "is_anonymous": False,
            },
            headers=auth_header(donor),
        ).json()

        client.post(
            "/payments/verify",
            json={
                "order_id":   init["order_id"],
                "payment_id": init["mock_payment_id"],
                "signature":  init["mock_signature"],
            },
            headers=auth_header(donor),
        )

        res = client.get(
            f"/payments/order/{init['order_id']}",
            headers=auth_header(donor),
        )
        assert res.status_code   == 200
        body = res.json()
        assert body["status"]           == "paid"
        assert body["transaction_id"] is not None
        assert body["transaction_id"].startswith("TXN-")

    def test_another_user_cannot_see_order(
        self, donor: User, another_donor: User, ngo_with_campaign
    ):
        """User B must NOT be able to see User A's order."""
        _, _, campaign, milestone = ngo_with_campaign

        init = client.post(
            "/payments/initiate",
            json={
                "campaign_id":  campaign.id,
                "milestone_id": milestone.id,
                "amount":       100.0,
                "is_anonymous": False,
            },
            headers=auth_header(donor),         # ← User A creates order
        ).json()

        res = client.get(
            f"/payments/order/{init['order_id']}",
            headers=auth_header(another_donor),  # ← User B tries to read it
        )
        assert res.status_code == 403

    def test_nonexistent_order_returns_404(self, donor: User):
        """Order that doesn't exist must return 404."""
        res = client.get(
            "/payments/order/MOCK_ORDER_DOESNOTEXIST99",
            headers=auth_header(donor),
        )
        assert res.status_code == 404

    def test_no_auth_returns_401(self):
        """Unauthenticated request must return 401."""
        res = client.get("/payments/order/MOCK_ORDER_DOESNOTEXIST99")
        assert res.status_code == 401
