from app.db.base import Base
from app.db.session import engine
from app.models.user import User
from app.models.ngo import NGO
from app.models.campaign import Campaign
from app.models.milestone import Milestone
from app.models.donation import Donation
from app.models.email_notification import EmailNotification
from app.models.proof import Proof
from app.models.refresh_token import RefreshToken
from app.models.email_verification import EmailVerification
from app.models.payment_order import PaymentOrder

def init_db():
    # Base.metadata.create_all(bind=engine)
    pass
