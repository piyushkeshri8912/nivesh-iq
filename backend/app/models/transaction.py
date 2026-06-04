from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.db.session import Base

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    symbol = Column(String(20), index=True, nullable=False)
    company_name = Column(String(100), nullable=True)
    transaction_type = Column(String(10), nullable=False) # BUY, SELL
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    executed_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    fees = Column(Float, default=0.0, nullable=False)
