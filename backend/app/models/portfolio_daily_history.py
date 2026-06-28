from sqlalchemy import Column, Integer, String, Date, Float, ForeignKey, UniqueConstraint
from app.db.session import Base

class PortfolioDailyHistory(Base):
    __tablename__ = "portfolio_daily_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    captured_at = Column(Date, nullable=False, index=True)
    total_value = Column(Float, nullable=False)
    total_cost = Column(Float, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "captured_at", name="uq_user_daily_history_captured_at"),
    )
