import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.core.config import settings
from app.api.router import api_router
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.models.user import User

# Configure global logging format for all backend modules
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def _ensure_vector_extension() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))




@asynccontextmanager
async def lifespan(app: FastAPI):
    # Enable pgvector extension before creating tables
    _ensure_vector_extension()
    # Startup DB schema creation
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

## CORS Configuration
# Parse whitelisted origins from settings
allowed_origins = []
if settings.ALLOWED_CORS_ORIGINS:
    allowed_origins = [origin.strip() for origin in settings.ALLOWED_CORS_ORIGINS.split(",") if origin.strip()]

# In production, allow Vercel subdomains dynamically to prevent circular dependencies
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if allowed_origins else ["http://localhost:3000"],
    allow_origin_regex=r"^(https://.*\.vercel\.app|http://localhost:3000)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)

if __name__ == "__main__":
    import uvicorn
    logging.info(f"Starting backend server")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
