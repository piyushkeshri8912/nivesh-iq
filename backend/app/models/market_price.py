from sqlalchemy import Column, String, Float, DateTime
from datetime import datetime
from app.db.session import Base

class MarketPrice(Base):
    __tablename__ = "market_prices"

    symbol = Column(String, primary_key=True, index=True)
    price = Column(Float, nullable=False)
    company_name = Column(String, nullable=True)
    sector = Column(String, nullable=True)
    market_cap = Column(Float, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

