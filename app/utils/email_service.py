import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587  # TLS port

def send_email(to_email: str, subject: str, body: str):
    msg = MIMEMultipart()
    msg["From"] = settings.SMTP_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    # Connect to Gmail SMTP server
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.set_debuglevel(1)  # <-- shows SMTP conversation
        server.starttls()
        server.login(settings.SMTP_EMAIL, settings.SMTP_PASSWORD)
        server.send_message(msg)
