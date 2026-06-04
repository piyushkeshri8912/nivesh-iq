import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from app.db.session import get_db
from app.models.user import User
from app.models.watchlist_item import WatchlistItem
from app.services.market_data_service import market_data_service
from app.services.news_service import news_service
from app.analytics.exposure import get_market_cap_bucket
from app.api.deps import get_current_user
from app.services.holdings_service import holdings_service

logger = logging.getLogger(__name__)

router = APIRouter()

class NewsItemResponse(BaseModel):
    symbol: str
    company_name: Optional[str] = None
    title: str
    link: str
    source: str
    published_at: str
    why_matters: str

@router.get("", response_model=List[NewsItemResponse])
def get_portfolio_news(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        from app.core.cache import cache_manager
        from fastapi.encoders import jsonable_encoder

        cache_key = f"user_cache:{current_user.id}:news"
        cached = cache_manager.get(cache_key)
        if cached is not None:
            return cached

        # 1. Retrieve user's active holdings dynamically
        holdings_res = holdings_service.calculate_holdings(db, current_user.id)
        holdings = holdings_res.holdings
        
        # 2. Retrieve user's watchlist items
        watchlist = (
            db.query(WatchlistItem)
            .filter(WatchlistItem.user_id == current_user.id)
            .all()
        )
        
        # Map holdings and watchlist details for context
        holdings_qty = {h.symbol.upper(): h.quantity for h in holdings}
        
        # Calculate returns dynamically using live prices
        watchlist_symbols = [w.symbol for w in watchlist]
        prices = market_data_service.get_prices_bulk(watchlist_symbols)
        watchlist_returns = {}
        for w in watchlist:
            sym = w.symbol.upper().strip()
            mkt_price = prices.get(w.symbol, 100.0)
            watchlist_returns[sym] = round(w.calculate_return(mkt_price), 2)

        
        # 3. Aggregate unique symbols and map to company names
        symbols_map = {}
        for h in holdings:
            sym = h.symbol.upper().strip()
            symbols_map[sym] = market_data_service.get_company_name(sym)
            
        for w in watchlist:
            sym = w.symbol.upper().strip()
            if sym not in symbols_map:
                symbols_map[sym] = w.company_name or market_data_service.get_company_name(sym)
                
        # 4. Fetch bulk news in parallel/sequence through feedparser cached pipeline
        bulk_news = news_service.fetch_news_bulk(symbols_map)
        
        # 5. Build enriched context-aware response
        enriched_feed = []
        for symbol, articles in bulk_news.items():
            comp_name = symbols_map.get(symbol, symbol)
            qty = holdings_qty.get(symbol, 0.0)
            ret_since_added = watchlist_returns.get(symbol)
            
            sector = market_data_service.get_sector(symbol)
            mkt_cap = market_data_service.get_market_cap(symbol)
            cap_bucket = get_market_cap_bucket(symbol, mkt_cap)
            
            # Calculate dynamic context commentary
            why_matters = news_service.get_why_matters_label(
                symbol=symbol,
                sector=sector,
                cap_bucket=cap_bucket,
                holding_qty=qty,
                return_since_added=ret_since_added
            )
            
            for art in articles:
                enriched_feed.append(
                    NewsItemResponse(
                        symbol=symbol,
                        company_name=comp_name,
                        title=art["title"],
                        link=art["link"],
                        source=art["source"],
                        published_at=art["published_at"],
                        why_matters=why_matters
                    )
                )
                
        # Sort chronological aggregations (published_at descending)
        enriched_feed.sort(key=lambda x: x.published_at, reverse=True)
        cache_manager.set(cache_key, jsonable_encoder(enriched_feed), ttl=600)
        return enriched_feed
    except Exception as e:
        logger.error(f"Failed to fetch portfolio news for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch portfolio news: {e}"
        )
