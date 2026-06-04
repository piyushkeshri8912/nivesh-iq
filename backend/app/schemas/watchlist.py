from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional

class WatchlistItemBase(BaseModel):
    symbol: str = Field(..., description="Stock Ticker Symbol (e.g. INFY.NS, AAPL)")

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        s = v.strip().upper()
        if not s:
            raise ValueError("Symbol cannot be empty")
        return s

class WatchlistItemCreate(WatchlistItemBase):
    pass

class WatchlistItemResponse(BaseModel):
    id: int
    user_id: str
    symbol: str
    company_name: Optional[str] = None
    market_price: Optional[float] = None
    sector: Optional[str] = None
    market_cap_bucket: Optional[str] = None
    price_at_added: Optional[float] = None
    return_since_added: Optional[float] = None
    added_at: datetime

    class Config:
        from_attributes = True

