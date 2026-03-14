from datetime import datetime, timedelta
from app.db.session import SessionLocal
from app.models.email_notification import EmailNotification
from app.models.refresh_token import RefreshToken

def cleanup_expired_emails():
    db = SessionLocal()
    db.query(EmailNotification)\
      .filter(EmailNotification.expires_at < datetime.utcnow())\
      .delete()
    db.commit()
    db.close()

def cleanup_refresh_tokens():
    db = SessionLocal()
    now = datetime.utcnow()
    db.query(RefreshToken)\
      .filter(RefreshToken.expires_at < now)\
      .delete()
    db.query(RefreshToken)\
      .filter(
          RefreshToken.revoked_at.isnot(None),
          RefreshToken.revoked_at < now - timedelta(days=1)
      )\
      .delete()
    db.commit()
    db.close()
