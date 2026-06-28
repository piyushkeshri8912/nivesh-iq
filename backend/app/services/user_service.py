import logging
from contextlib import contextmanager
from typing import Dict, Any, List, Set

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.user_profile import UserProfile
from app.models.watchlist_item import WatchlistItem
from app.services.holdings_service import holdings_service
from app.services.market_data_service import market_data_service
from app.analytics.exposure import (
    calculate_market_cap_exposure,
    calculate_sector_exposure,
)

logger = logging.getLogger(__name__)


@contextmanager
def db_session():
    """Context manager for safe database session lifecycle handling."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _load_user_profile(db: Session, user_id: str) -> Dict[str, Any]:
    profile_obj = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    profile_data = {
        "full_name": getattr(profile_obj, "full_name", None),
        "profession": getattr(profile_obj, "profession", None),
        "risk_appetite": getattr(profile_obj, "risk_appetite", None),
        "time_horizon": getattr(profile_obj, "time_horizon", None),
        "investment_goal": getattr(profile_obj, "investment_goal", None),
        "monthly_investment_budget": getattr(profile_obj, "monthly_investment_budget", None),
    }
    missing_fields = [
        field
        for field in ["risk_appetite", "time_horizon", "investment_goal", "monthly_investment_budget"]
        if not profile_data.get(field)
    ]
    profile_data["missing_fields"] = missing_fields
    return profile_data


def _load_watchlist_snapshot(db: Session, user_id: str) -> Dict[str, Any]:
    watchlist_rows = db.query(WatchlistItem).filter(WatchlistItem.user_id == user_id).all()
    watchlist = []
    watchlist_symbols = [row.symbol for row in watchlist_rows]
    watchlist_prices = {}
    if watchlist_symbols:
        try:
            watchlist_prices = market_data_service.get_prices_bulk(watchlist_symbols)
        except Exception as e:
            logger.error(f"Failed bulk price fetch for watchlist: {e}")
    
    for row in watchlist_rows:
        price = watchlist_prices.get(row.symbol, 100.0)
        watchlist.append({
            "symbol": row.symbol,
            "company_name": row.company_name or row.symbol,
            "market_price": round(price, 2),
            "return_since_added": round(row.calculate_return(price), 2)
        })
    return {
        "watchlist": watchlist,
        "watchlist_symbols": watchlist_symbols,
        "watchlist_count": len(watchlist)
    }


def _load_portfolio_snapshot(db: Session, user_id: str, max_holdings: int = 5) -> Dict[str, Any]:
    holdings_res = holdings_service.calculate_holdings(db, user_id)
    top_holdings_raw = holdings_res.holdings[:max_holdings]

    symbols = [h.symbol for h in top_holdings_raw]
    try:
        sectors_by_symbol = market_data_service.get_sectors_bulk(symbols)
    except Exception as e:
        logger.error(f"Bulk sector fetch failed: {e}")
        sectors_by_symbol = {}

    top_holdings: List[Dict[str, Any]] = []
    sector_labels: Set[str] = set()

    for holding in top_holdings_raw:
        sector = sectors_by_symbol.get(holding.symbol)
        if sector is None:
            try:
                sector = market_data_service.get_sector(holding.symbol)
            except Exception as e:
                logger.error(f"Sector fetch failed for {holding.symbol}: {e}")
                sector = "Unknown"

        sector_labels.add(sector)
        top_holdings.append(
            {
                "symbol": holding.symbol,
                "company_name": holding.company_name,
                "quantity": round(holding.quantity, 4),
                "average_buy_price": round(holding.average_buy_price, 2),
                "market_price": round(holding.market_price, 2),
                "market_value": round(holding.market_value, 2),
                "allocation_percent": round(holding.allocation_percent, 2),
                "unrealized_pnl": round(holding.unrealized_pnl, 2),
                "sector": sector,
            }
        )


    watchlist_snapshot = _load_watchlist_snapshot(db, user_id)

    return {
        "summary": holdings_res.summary.model_dump(),
        "top_holdings": top_holdings,
        "holdings_count": len(holdings_res.holdings),
        "top_tickers": [holding["symbol"] for holding in top_holdings],
        "sectors": sorted(sector_labels),
        "sector_exposure": calculate_sector_exposure(db, user_id),
        "market_cap_exposure": calculate_market_cap_exposure(db, user_id),
    }


