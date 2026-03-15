from pydantic_settings import BaseSettings
from pydantic import ConfigDict
import json

class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env")
    DATABASE_URL: str
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 1
    REDIS_URL: str = "redis://localhost:6379/0"
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_MAX_REQUESTS: int = 20
    CLOUDINARY_CLOUD_NAME: str
    CLOUDINARY_API_KEY: str
    CLOUDINARY_API_SECRET: str
    SMTP_EMAIL: str
    SMTP_PASSWORD: str
    FERNET_KEY: str
    CORS_ORIGINS: str = "http://localhost:3000"
    FRONTEND_URL: str = "http://localhost:3000"
    CORS_ALLOW_VERCEL_PREVIEWS: bool = True
    EMAIL_VERIFICATION_EXPIRE_HOURS: int = 24
    PASSWORD_RESET_EXPIRE_HOURS: int = 2

    def get_cors_origins(self) -> list[str]:
        raw = (self.CORS_ORIGINS or "").strip()

        origins: list[str] = []
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    origins.extend(str(origin).strip() for origin in parsed if str(origin).strip())
            except json.JSONDecodeError:
                pass

        if not origins:
            origins.extend(origin.strip() for origin in raw.split(",") if origin.strip())

        if self.FRONTEND_URL and self.FRONTEND_URL.strip():
            origins.append(self.FRONTEND_URL.strip())

        unique_origins: list[str] = []
        seen: set[str] = set()
        for origin in origins:
            if origin not in seen:
                unique_origins.append(origin)
                seen.add(origin)

        return unique_origins

    def get_cors_origin_regex(self) -> str | None:
        if self.CORS_ALLOW_VERCEL_PREVIEWS:
            return r"https://([a-zA-Z0-9-]+\.)*vercel\.app"
        return None


settings = Settings()
