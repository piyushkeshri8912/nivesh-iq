from sqlalchemy.orm import Session
from typing import List, Dict
from app.services.holdings_service import holdings_service
from app.services.market_data_service import market_data_service

# Configurable buckets based on asset currencies
MARKET_CAP_THRESHOLD_INR = {
    "LARGE": 200000000000.0,  # ₹20,000 Crores
    "MID": 50000000000.0,     # ₹5,000 Crores
}

def get_market_cap_bucket(symbol: str, market_cap: float | None) -> str:
    if market_cap is None:
        return "ETFs & Others"
    symbol = symbol.upper().strip()
    thresholds = MARKET_CAP_THRESHOLD_INR
    if market_cap >= thresholds["LARGE"]:
        return "LARGE"
    elif market_cap >= thresholds["MID"]:
        return "MID"
    else:
        return "SMALL"

def calculate_sector_exposure(db: Session, user_id: str) -> List[Dict]:
    res = holdings_service.calculate_holdings(db, user_id)
    sector_sums = {}
    total_val = res.summary.total_value

    for h in res.holdings:
        sector = market_data_service.get_sector(h.symbol, db=db)
        sector_sums[sector] = sector_sums.get(sector, 0.0) + h.market_value

    exposure = []
    for sector, val in sector_sums.items():
        percentage = (val / total_val * 100.0) if total_val > 0 else 0.0
        exposure.append({
            "sector": sector,
            "value": val,
            "percentage": percentage
        })
    exposure.sort(key=lambda x: x["percentage"], reverse=True)
    return exposure

def calculate_market_cap_exposure(db: Session, user_id: str) -> List[Dict]:
    res = holdings_service.calculate_holdings(db, user_id)
    cap_sums = {"LARGE": 0.0, "MID": 0.0, "SMALL": 0.0, "ETFs & Others": 0.0}
    total_val = res.summary.total_value

    for h in res.holdings:
        cap_val = market_data_service.get_market_cap(h.symbol, db=db)
        bucket = get_market_cap_bucket(h.symbol, cap_val)
        cap_sums[bucket] += h.market_value

    exposure = []
    for bucket, val in cap_sums.items():
        percentage = (val / total_val * 100.0) if total_val > 0 else 0.0
        exposure.append({
            "bucket": bucket,
            "value": val,
            "percentage": percentage
        })
    return exposure
