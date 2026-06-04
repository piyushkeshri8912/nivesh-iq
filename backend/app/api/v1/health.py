import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
def check_health(db: Session = Depends(get_db)):
    db_ok = False
    try:
        # Using a shallow, fast query to check connectivity
        db.execute(text("SELECT 1"))
        db_ok = True
        logger.info("Health check passed: Database connection is healthy.")
    except Exception as e:
        logger.exception("Health check failed: Database connection error occurred.")

    # Prepare response payload
    response_data = {
        "status": "healthy" if db_ok else "unhealthy",
        "database": "connected" if db_ok else "disconnected",
        "api_version": "v1",
    }

    # If DB is down, return a 503 Service Unavailable status code
    if not db_ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=response_data,
        )

    return response_data