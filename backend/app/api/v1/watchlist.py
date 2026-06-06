import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.db.session import get_db
from app.models.user import User
from app.models.watchlist_item import WatchlistItem
from app.schemas.watchlist import WatchlistItemCreate, WatchlistItemResponse
from app.services.market_data_service import market_data_service
from app.analytics.exposure import get_market_cap_bucket
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

# --- ROUTE HANDLERS ---

@router.get("", response_model=List[WatchlistItemResponse])
def get_watchlist(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        from app.core.cache import cache_manager
        from fastapi.encoders import jsonable_encoder

        cache_key = f"user_cache:{current_user.id}:watchlist"
        cached = cache_manager.get(cache_key)
        if cached is not None:
            return cached
        watchlist_items = (
            db.query(WatchlistItem)
            .filter(WatchlistItem.user_id == current_user.id)
            .order_by(WatchlistItem.added_at.desc())
            .all()
        )
        
        # Pre-fetch live prices in bulk for performance (satisfies the price caching request)
        symbols = [item.symbol for item in watchlist_items]
        prices = market_data_service.get_prices_bulk(symbols)
        
        db_updated = False
        response = []
        for item in watchlist_items:
            symbol = item.symbol
            mkt_price = prices.get(symbol, 100.0)
            sector = market_data_service.get_sector(symbol)
            mkt_cap = market_data_service.get_market_cap(symbol)
            cap_bucket = get_market_cap_bucket(symbol, mkt_cap)
            # Calculate return since added dynamically
            return_pct = item.calculate_return(mkt_price)
            rounded_pct = round(return_pct, 2)

            # Update database column to keep DB in sync with live calculations
            if item.return_since_added != rounded_pct:
                item.return_since_added = rounded_pct
                db_updated = True

            response.append(
                WatchlistItemResponse(
                    id=item.id,
                    user_id=item.user_id,
                    symbol=symbol,
                    company_name=item.company_name,
                    market_price=mkt_price,
                    sector=sector,
                    market_cap_bucket=cap_bucket,
                    price_at_added=item.price_at_added or mkt_price,
                    return_since_added=rounded_pct,
                    added_at=item.added_at
                )
            )
        
        if db_updated:
            db.commit()
            
        cache_manager.set(cache_key, jsonable_encoder(response), ttl=60) # 1 minute cache
        return response
    except Exception as e:
        logger.error(f"Failed to fetch watchlist for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch watchlist: {e}"
        )

@router.post("", response_model=WatchlistItemResponse)
def add_watchlist_item(
    item_in: WatchlistItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        symbol = item_in.symbol.upper().strip()
        if not symbol.endswith(".NS"):
            symbol = f"{symbol}.NS"
        
        # Check if already exists on user's watchlist
        existing = (
            db.query(WatchlistItem)
            .filter(WatchlistItem.user_id == current_user.id, WatchlistItem.symbol == symbol)
            .first()
        )
        if existing:
            logger.warning(f"User {current_user.id} attempted to add duplicate symbol {symbol} to watchlist")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{symbol} is already on your watchlist"
            )
        
        # Auto-resolve company name and current price via yfinance
        company_name = market_data_service.get_company_name(symbol)
        price_at_added = market_data_service.get_price(symbol)
        
        db_item = WatchlistItem(
            user_id=current_user.id,
            symbol=symbol,
            company_name=company_name,
            price_at_added=price_at_added,
            return_since_added=0.0
        )
        db.add(db_item)
        db.commit()
        db.refresh(db_item)
        
        from app.core.cache import cache_manager
        cache_manager.invalidate_user_cache(current_user.id)
        logger.info(f"Successfully added {symbol} to watchlist for user {current_user.id}")
        
        # Enrich the returned response item
        mkt_price = market_data_service.get_price(symbol)
        sector = market_data_service.get_sector(symbol)
        mkt_cap = market_data_service.get_market_cap(symbol)
        cap_bucket = get_market_cap_bucket(symbol, mkt_cap)
        
        return WatchlistItemResponse(
            id=db_item.id,
            user_id=db_item.user_id,
            symbol=db_item.symbol,
            company_name=db_item.company_name,
            market_price=mkt_price,
            sector=sector,
            market_cap_bucket=cap_bucket,
            price_at_added=db_item.price_at_added,
            return_since_added=0.0,
            added_at=db_item.added_at
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to add watchlist item for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add watchlist item: {e}"
        )

@router.delete("/{item_id}")
def delete_watchlist_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        db_item = (
            db.query(WatchlistItem)
            .filter(WatchlistItem.id == item_id, WatchlistItem.user_id == current_user.id)
            .first()
        )
        if not db_item:
            logger.warning(f"Watchlist item {item_id} not found for deletion by user {current_user.id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Watchlist item not found"
            )
        db.delete(db_item)
        db.commit()

        from app.core.cache import cache_manager
        cache_manager.invalidate_user_cache(current_user.id)
        logger.info(f"Successfully deleted watchlist item {item_id} for user {current_user.id}")

        return {"message": "Watchlist item removed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete watchlist item {item_id} for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete watchlist item: {e}"
        )