# OLD
class Settings(BaseSettings):
    class Config:
        env_file = ".env"

# NEW
from pydantic_settings import BaseSettings
from pydantic import ConfigDict

class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env")