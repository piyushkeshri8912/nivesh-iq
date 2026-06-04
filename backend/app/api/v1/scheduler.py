from fastapi import APIRouter, Header, HTTPException, status
from app.services.market_data_service import market_data_service
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/refresh-market-data")
def refresh_market_data(
    x_cloudscheduler: str = Header(None, alias="X-CloudScheduler")
):
    """
    Endpoint intended to be hit by Google Cloud Scheduler to trigger market data updates.
    Google Cloud automatically attaches the 'X-CloudScheduler: true' header to its requests.
    This header is stripped from external internet traffic, ensuring identity security.
    """
    if not x_cloudscheduler:
        logger.warning("Attempted to trigger market data refresh without Cloud Scheduler headers.")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied. Must be triggered by Cloud Scheduler.")
        
    market_data_service.update_all_prices_in_db()
    return {"status": "success", "message": "Bulk market data refresh triggered successfully."}
