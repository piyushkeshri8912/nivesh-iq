import pytest
from fastapi import HTTPException
from app.api.deps import check_guest_token_limit
from app.models.user import User
from app.models.chat import ChatSession
from app.models.portfolio_review import PortfolioReview
from app.core.cache import cache_manager
from sqlalchemy.orm import Session

def test_guest_token_limit_not_exceeded(db: Session, guest_user: User):
    # Under limit: 5000 + 5000 = 10,000 < 20,000
    sess = ChatSession(id="session-1", user_id=guest_user.id, total_tokens=5000)
    rev = PortfolioReview(
        user_id=guest_user.id,
        risk_summary="Low risk",
        diversification_summary="High diversification",
        total_tokens=5000
    )
    db.add(sess)
    db.add(rev)
    db.commit()

    # Should not raise exception
    check_guest_token_limit(db, guest_user)

def test_guest_token_limit_exceeded(db: Session, guest_user: User):
    # Exceeded: 15,000 + 10,000 = 25,000 > 20,000
    sess = ChatSession(id="session-2", user_id=guest_user.id, total_tokens=15000)
    rev = PortfolioReview(
        user_id=guest_user.id,
        risk_summary="Low risk",
        diversification_summary="High diversification",
        total_tokens=10000
    )
    db.add(sess)
    db.add(rev)
    db.commit()

    # Should raise HTTP 403 Forbidden
    with pytest.raises(HTTPException) as exc_info:
        check_guest_token_limit(db, guest_user)
    assert exc_info.value.status_code == 403
    assert "token limit" in exc_info.value.detail

def test_registered_user_ignores_guest_token_limit(db: Session, test_user: User):
    # Registered user with 30,000 tokens should be ignored
    sess = ChatSession(id="session-3", user_id=test_user.id, total_tokens=25000)
    rev = PortfolioReview(
        user_id=test_user.id,
        risk_summary="Low risk",
        diversification_summary="High diversification",
        total_tokens=10000
    )
    db.add(sess)
    db.add(rev)
    db.commit()

    # Should not raise exception
    check_guest_token_limit(db, test_user)

def test_cache_invalidation_lifecycle():
    user_id = "test-user-id"
    cache_key_txs = f"user_cache:{user_id}:transactions"
    cache_key_holdings = f"user_cache:{user_id}:holdings"
    
    # Store some mock cache data
    cache_manager.set(cache_key_txs, [{"id": 1}])
    cache_manager.set(cache_key_holdings, {"total_value": 50000.0})
    
    # Verify cached values are set
    assert cache_manager.get(cache_key_txs) == [{"id": 1}]
    assert cache_manager.get(cache_key_holdings) == {"total_value": 50000.0}
    
    # Invalidate cache for the user
    cache_manager.invalidate_user_cache(user_id)
    
    # Verify they are deleted
    assert cache_manager.get(cache_key_txs) is None
    assert cache_manager.get(cache_key_holdings) is None
