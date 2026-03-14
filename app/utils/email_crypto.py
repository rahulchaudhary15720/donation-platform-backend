from cryptography.fernet import Fernet
from app.core.config import settings

cipher = Fernet(settings.FERNET_KEY.encode())

def encrypt_email(email: str) -> str:
    return cipher.encrypt(email.encode()).decode()

def decrypt_email(encrypted_email: str) -> str:
    return cipher.decrypt(encrypted_email.encode()).decode()
