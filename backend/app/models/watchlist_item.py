from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from app.db.session import Base

class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    symbol = Column(String(20), index=True, nullable=False)
    company_name = Column(String(100), nullable=True)
    added_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    return_since_added = Column(Float, nullable=True)
    price_at_added = Column(Float, nullable=True)
    __table_args__ = (
        UniqueConstraint("user_id", "symbol", name="uq_user_watchlist_symbol"),
    )

    def calculate_return(self, current_price: float) -> float:
        price_added = self.price_at_added or current_price
        if price_added and price_added > 0:
            return ((current_price - price_added) / price_added) * 100.0
        return 0.0

