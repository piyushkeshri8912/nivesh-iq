import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.user import User
from app.schemas.portfolio import PortfolioHoldingsListResponse
from app.services.holdings_service import holdings_service
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/holdings", response_model=PortfolioHoldingsListResponse)
def get_holdings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        from app.core.cache import cache_manager
        from fastapi.encoders import jsonable_encoder

        cache_key = f"user_cache:{current_user.id}:holdings"
        cached = cache_manager.get(cache_key)
        if cached is not None:
            return cached

        res = holdings_service.calculate_holdings(db, current_user.id)
        # Cache the JSON-serializable version of the response
        cache_manager.set(cache_key, jsonable_encoder(res), ttl=300)
        return res
    except Exception as e:
        logger.error(f"Failed to calculate holdings for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate holdings: {e}"
        )
