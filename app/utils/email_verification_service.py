"""
Email Verification Service
Handles sending verification emails and token generation
"""
import secrets
from datetime import datetime, timedelta
from app.core.config import settings
from app.utils.email_service import send_email

def generate_verification_token() -> str:
    """Generate a secure random verification token"""
    return secrets.token_urlsafe(32)

def send_verification_email(email: str, token: str):
    """Send verification email to user"""
    verification_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    
    subject = "Verify Your Email - Donation & Charity Platform"
    
    body = f"""
Hello,

Thank you for registering with Donation & Charity Platform!

Please verify your email address by clicking the link below:

{verification_url}

This link will expire in {settings.EMAIL_VERIFICATION_EXPIRE_HOURS} hours.

If you didn't create an account, please ignore this email.

Best regards,
Donation & Charity Platform Team
    """
    
    send_email(email, subject, body)


def send_deactivation_email(email: str, role: str):
    """Send notification email when an account is deactivated by admin"""
    subject = "Your account has been deactivated"

    body = f"""
Hello,

Your {role} account on the Donation & Charity Platform has been deactivated by an administrator.

If you believe this is a mistake, please contact our support team.

Best regards,
Donation & Charity Platform Team
    """

    send_email(email, subject, body)
def send_password_reset_email(email: str, token: str):
    """Send password reset email to user"""
    reset_url = f"{settings.FRONTEND_URL.rstrip('/')}/auth/reset-password?token={token}"

    subject = "Password Reset Request - Donation & Charity Platform"

    body = f"""
Hello,

We received a request to reset the password for your account.

Click the link below to set a new password:

{reset_url}

This link will expire in 30 minutes.

If you did not request a password reset, please ignore this email.
Your password will remain unchanged.

Best regards,
Donation & Charity Platform Team
    """

    send_email(email, subject, body)


def send_welcome_email(email: str, role: str):
    """Send welcome email after successful verification"""
    subject = "Welcome to Donation & Charity Platform!"
    
    role_message = {
        "user": "You can now start donating to campaigns and making a difference!",
        "ngo": "Your NGO account is pending admin approval. You'll be able to create campaigns once approved.",
        "admin": "You have full administrative access to the platform."
    }
    
    body = f"""
Hello,

Your email has been verified successfully!

{role_message.get(role, "Welcome to our platform!")}

You can now log in at: {settings.FRONTEND_URL}/login

Best regards,
Donation & Charity Platform Team
    """
    
    send_email(email, subject, body)
