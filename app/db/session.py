from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from urllib.parse import quote_plus

# URL-encode the password to handle special characters
def get_encoded_database_url(url: str) -> str:
    """Encode special characters in database URL password"""
    if '://' in url and '@' in url:
        # Extract parts: postgresql://user:password@host:port/db
        scheme = url.split('://')[0]
        rest = url.split('://')[1]
        
        if '@' in rest:
            creds, location = rest.split('@', 1)
            if ':' in creds:
                user, password = creds.split(':', 1)
                # Encode the password
                encoded_password = quote_plus(password)
                return f"{scheme}://{user}:{encoded_password}@{location}"
    return url

encoded_url = get_encoded_database_url(settings.DATABASE_URL)

# Create engine with connection pooling and timeout settings
engine = create_engine(
    encoded_url,
    connect_args={
        "connect_timeout": 10,
        "options": "-c timezone=utc"
    },
    pool_pre_ping=True,  # Verify connections before using them
    pool_size=5,  # Connection pool size
    max_overflow=10,  # Max connections beyond pool_size
    echo=False  # Set to True for SQL query logging
)
SessionLocal = sessionmaker(bind=engine, autoflush=False)
