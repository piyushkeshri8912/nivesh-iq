import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from app.db.session import get_db
from app.models.user import User
from app.analytics.exposure import calculate_sector_exposure, calculate_market_cap_exposure
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/exposures")
def get_exposures(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        from app.core.cache import cache_manager
        from fastapi.encoders import jsonable_encoder

        cache_key = f"user_cache:{current_user.id}:exposures"
        cached = cache_manager.get(cache_key)
        if cached is not None:
            return cached

        sectors = calculate_sector_exposure(db, current_user.id)
        caps = calculate_market_cap_exposure(db, current_user.id)
        res = {
            "sectors": sectors,
            "market_caps": caps
        }
        cache_manager.set(cache_key, jsonable_encoder(res), ttl=300)
        return res
    except Exception as e:
        logger.error(f"Failed to calculate exposures for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate exposures: {e}"
        )

@router.get("/performance-history")
def get_performance_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Calculate and return the dynamic in-memory portfolio daily performance history on demand,
    guaranteeing zero lag and eliminating the need for stored snapshot tables.
    """
    try:
        from app.core.cache import cache_manager
        from fastapi.encoders import jsonable_encoder

        cache_key = f"user_cache:{current_user.id}:performance_history"
        cached = cache_manager.get(cache_key)
        if cached is not None:
            return cached

        from app.services.portfolio_history_service import portfolio_history_service
        res = portfolio_history_service.calculate_historical_performance(db, current_user.id)
        cache_manager.set(cache_key, jsonable_encoder(res), ttl=300)
        return res
    except Exception as e:
        logger.error(f"Failed to calculate performance history for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate performance history: {e}"
        )
