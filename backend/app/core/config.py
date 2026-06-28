import os
import json
import tempfile
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
    GOOGLE_APPLICATION_CREDENTIALS: str
    NEON_AUTH_BASE_URL: str
    NEON_AUTH_COOKIE_SECRET: str    
    REDIS_URL: str = "redis://localhost:6379"
    ALLOWED_CORS_ORIGINS: Optional[str] = ""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

settings = Settings()

if settings.GOOGLE_APPLICATION_CREDENTIALS:
    cred_value = settings.GOOGLE_APPLICATION_CREDENTIALS.strip()
    
    # Strip surrounding single/double quotes if present from env loading
    if (cred_value.startswith("'") and cred_value.endswith("'")) or (cred_value.startswith('"') and cred_value.endswith('"')):
        cred_value = cred_value[1:-1].strip()

    if cred_value.startswith('{'):
        try:
            # Validate and parse JSON
            cred_dict = json.loads(cred_value)
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, prefix="gcp_creds_"
            )
            json.dump(cred_dict, tmp)
            tmp.close()
            cred_path = tmp.name
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_path
            logger.info("Inlined GOOGLE_APPLICATION_CREDENTIALS written to temp file: %s", cred_path)
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to write inline GOOGLE_APPLICATION_CREDENTIALS: %s", e)
    else:
        # Check if it's a file path
        if os.path.exists(cred_value):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_value
            logger.info("Using GOOGLE_APPLICATION_CREDENTIALS file path: %s", cred_value)
        else:
            logger.warning("GOOGLE_APPLICATION_CREDENTIALS is not valid inline JSON and path does not exist: %s", cred_value)
else:
    logger.warning("Google Credentials not specified. Relying on GCP Application Default Credentials (ADC).")
