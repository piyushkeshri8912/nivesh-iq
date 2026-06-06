import os
import logging
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    PROJECT_NAME: str = "NiveshIQ AI Portfolio Intelligence Engine"
    API_V1_STR: str = "/api/v1"
    DATABASE_URL: str
    
    # Vertex AI Settings (Phase 6+)
    VERTEX_PROJECT_ID: str
    VERTEX_LOCATION: str = "global"
    VERTEX_FLASH_LITE_MODEL: str = "gemini-2.5-flash-lite"
    VERTEX_FLASH_MODEL: str = "gemini-2.5-flash"
    VERTEX_PRO_MODEL: str = "gemini-2.5-pro"
    VERTEX_EMBEDDINGS_MODEL: str = "text-embedding-004"
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None
    NEON_AUTH_BASE_URL: str
    NEON_AUTH_COOKIE_SECRET: str    
    REDIS_URL: str = "redis://localhost:6379"
    BACKEND_CORS_ORIGINS: str = "http://localhost:3000;http://127.0.0.1:3000;https://niveshiq-frontend-mjqaylfdnq-uc.a.run.app"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

settings = Settings()

# Explicitly inject the credentials path into the OS environment if the file exists,
# otherwise let GCP libraries fall back to Application Default Credentials (ADC).
if settings.GOOGLE_APPLICATION_CREDENTIALS and os.path.exists(settings.GOOGLE_APPLICATION_CREDENTIALS):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = settings.GOOGLE_APPLICATION_CREDENTIALS
    logger.info(f"Google Credentials file initialized from: {settings.GOOGLE_APPLICATION_CREDENTIALS}")
else:
    logger.warning("Google Credentials file not found or not specified. Relying on GCP Application Default Credentials (ADC).")
