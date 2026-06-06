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


def _ensure_user_memory_vector_schema() -> None:
    check_sql = text(
        """
        SELECT udt_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'user_memories'
          AND column_name = 'embedding';
        """
    )
    with engine.begin() as conn:
        result = conn.execute(check_sql).mappings().first()
        if not result:
            return
        if result["udt_name"] in {"json", "jsonb"}:
            conn.execute(text(
                """
                ALTER TABLE public.user_memories
                ALTER COLUMN embedding TYPE vector(768)
                USING embedding::text::vector(768);
                """
            ))

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Enable pgvector extension before creating tables
    _ensure_vector_extension()
    # Startup DB schema creation
    Base.metadata.create_all(bind=engine)
    # Fix legacy json/jsonb embedding column if needed
    _ensure_user_memory_vector_schema()
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# Configure CORS dynamically from settings
origins = [o.strip() for o in settings.BACKEND_CORS_ORIGINS.split(";") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https?://.*\.run\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)

if __name__ == "__main__":
    import uvicorn
    logging.info(f"Starting backend server")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
