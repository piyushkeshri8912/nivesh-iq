import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.db.session import get_db
from app.models.user import User
from app.models.portfolio_review import PortfolioReview
from app.schemas.insights import PortfolioReviewResponse
from app.services.insights_engine import insights_engine
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("", response_model=Optional[PortfolioReviewResponse])
def get_latest_portfolio_review(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve the latest generated AI Portfolio Review from PostgreSQL.
    """
    try:
        review = (
            db.query(PortfolioReview)
            .filter(PortfolioReview.user_id == current_user.id)
            .order_by(PortfolioReview.created_at.desc())
            .first()
        )
        return review
    except Exception as e:
        logger.error(f"Failed to retrieve portfolio review for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve portfolio review: {e}"
        )

@router.post("/generate", response_model=PortfolioReviewResponse)
def generate_portfolio_review(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Execute the LangGraph AI workflow using Vertex AI models,
    save the compiled report in PostgreSQL, and return the report.
    """
    try:
        logger.info(f"Starting portfolio review generation for user {current_user.id}")
        report = insights_engine.generate_review(db, current_user.id)
        logger.info(f"Successfully generated portfolio review for user {current_user.id}")
        return report
    except Exception as e:
        logger.error(f"AI Insights generation failed for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI Insights generation failed: {e}"
        )
