from pydantic import BaseModel
from datetime import datetime
from typing import List, Dict, Any, Optional

class PortfolioReviewResponse(BaseModel):
    id: int
    user_id: str
    created_at: datetime
    
    risk_summary: str
    diversification_summary: str
    
    rebalancing_ideas: Optional[List[Dict[str, Any]]] = []
    potential_stock_picks: Optional[List[Dict[str, Any]]] = []
    warnings: Optional[List[Dict[str, Any]]] = []
    market_impact: Optional[str] = None
    
    evidence: Optional[Dict[str, Any]] = None
    disclaimers: Optional[str] = None

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


    class Config:
        from_attributes = True
