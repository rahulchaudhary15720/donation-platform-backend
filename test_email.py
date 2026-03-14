from app.utils.email_service import send_email

send_email(
    "2022csrohan13203@poornima.edu.in", 
    "Test Email", 
    "Hello! This is a test from FastAPI."
)
print("Email sent!")
