from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, JSON
from sqlalchemy.sql import func
from app.db.session import Base

class PortfolioReview(Base):
    __tablename__ = "portfolio_reviews"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    
    risk_summary = Column(Text, nullable=False)
    diversification_summary = Column(Text, nullable=False)
    
    rebalancing_ideas = Column(JSON, nullable=True)
    potential_stock_picks = Column(JSON, nullable=True)
    warnings = Column(JSON, nullable=True)
    market_impact = Column(Text, nullable=True)
    
    evidence = Column(JSON, nullable=True)
    disclaimers = Column(Text, nullable=True)

    # Token usage tracking
    prompt_tokens = Column(Integer, default=0, nullable=False)
    completion_tokens = Column(Integer, default=0, nullable=False)
    total_tokens = Column(Integer, default=0, nullable=False)

