import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env")

    PROJECT_NAME: str = "FinTech Multi-Currency Ledger API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Secret Key for JWT
    SECRET_KEY: str = "fintech_ultra_secure_jwt_secret_key_change_in_production_998877"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./fintech_ledger.db")
    
    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Celery
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
    
    # External Exchange Rate API
    EXCHANGE_RATE_API_URL: str = "https://open.er-api.com/v6/latest"
    FX_CACHE_TTL_SECONDS: int = 300  # 5 minutes
    QUOTE_VALIDITY_SECONDS: int = 60   # 60 seconds guaranteed rate lock
    
    # PDF Storage Path
    STORAGE_DIR: str = os.getenv("STORAGE_DIR", "./storage/statements")
    
    # Supported Currencies
    SUPPORTED_CURRENCIES: List[str] = ["USD", "GHS", "GBP"]


settings = Settings()
