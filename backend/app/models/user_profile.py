from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.db.session import Base

class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)

    full_name = Column(String, nullable=True)
    dob = Column(String, nullable=True)
    profession = Column(String, nullable=True)

    risk_appetite = Column(String, nullable=False)  # CONSERVATIVE, MODERATE, AGGRESSIVE
    time_horizon = Column(String, nullable=False)   # SHORT_TERM, MEDIUM_TERM, LONG_TERM
    investment_goal = Column(String, nullable=False) # WEALTH_ACCUMULATION, RETIREMENT, INCOME, BALANCED
    monthly_investment_budget = Column(Float, nullable=True)

    user = relationship("User", back_populates="profile")
