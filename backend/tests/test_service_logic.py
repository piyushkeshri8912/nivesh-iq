import pytest
from datetime import datetime, date, timedelta
from app.services.holdings_service import holdings_service
from app.services.portfolio_history_service import portfolio_history_service
from app.services.market_data_service import market_data_service
from app.models.transaction import Transaction
from app.models.user import User
from app.models.portfolio_daily_history import PortfolioDailyHistory
from sqlalchemy.orm import Session

def test_holdings_calculation_no_transactions(db: Session, test_user: User):
    res = holdings_service.calculate_holdings(db, test_user.id)
    assert res.holdings == []
    assert res.summary.total_cost == 0.0
    assert res.summary.total_value == 0.0

def test_holdings_calculation_buy_and_sell(db: Session, test_user: User, mocker):
    # Mock market price lookup
    mock_meta = mocker.patch("app.services.market_data_service.market_data_service.get_metadata_bulk")
    mock_meta.return_value = {
        "INFY.NS": {
            "price": 1200.0,
            "company_name": "Infosys",
            "sector": "Technology"
        }
    }

    # 1. Buy transaction
    tx_buy = Transaction(
        user_id=test_user.id,
        symbol="INFY.NS",
        company_name="Infosys",
        transaction_type="BUY",
        quantity=10.0,
        price=1000.0,  # total cost = 10000.0
        fees=50.0,     # cost basis including fee = 10050.0 / avg = 1005.0
        executed_at=datetime.now() - timedelta(days=2)
    )
    db.add(tx_buy)

    # 2. Sell transaction
    tx_sell = Transaction(
        user_id=test_user.id,
        symbol="INFY.NS",
        company_name="Infosys",
        transaction_type="SELL",
        quantity=5.0,
        price=1100.0,  # realized profit = 5 * (1100 - 1005) - 20 = 475 - 20 = 455
        fees=20.0,
        executed_at=datetime.now() - timedelta(days=1)
    )
    db.add(tx_sell)
    db.commit()

    res = holdings_service.calculate_holdings(db, test_user.id)
    assert len(res.holdings) == 1
    holding = res.holdings[0]
    assert holding.symbol == "INFY.NS"
    assert holding.quantity == 5.0
    assert holding.average_buy_price == 1005.0
    assert holding.market_price == 1200.0
    assert holding.market_value == 6000.0
    assert holding.unrealized_pnl == 975.0  # 5 * (1200 - 1005) = 975.0

    assert res.summary.total_cost == 5025.0  # 5 * 1005.0
    assert res.summary.total_value == 6000.0
    assert res.summary.total_realized_pnl == 455.0

def test_rebuild_history_logic(db: Session, test_user: User, mocker):
    # Mock historical prices
    mock_history = mocker.patch("app.services.market_data_service.market_data_service.get_historical_prices_bulk")
    
    start_date = date.today() - timedelta(days=3)
    mock_history.return_value = {
        "INFY.NS": {
            (start_date + timedelta(days=0)).strftime("%Y-%m-%d"): 1000.0,
            (start_date + timedelta(days=1)).strftime("%Y-%m-%d"): 1050.0,
            (start_date + timedelta(days=2)).strftime("%Y-%m-%d"): 1100.0,
            (start_date + timedelta(days=3)).strftime("%Y-%m-%d"): 1150.0
        }
    }

    # Pre-seed transaction on start_date
    tx = Transaction(
        user_id=test_user.id,
        symbol="INFY.NS",
        company_name="Infosys",
        transaction_type="BUY",
        quantity=10.0,
        price=1000.0,
        fees=0.0,
        executed_at=datetime.combine(start_date, datetime.min.time())
    )
    db.add(tx)
    db.commit()

    # Rebuild history
    portfolio_history_service.rebuild_history(
        db, 
        test_user.id, 
        from_date=datetime.combine(start_date, datetime.min.time()), 
        force=True
    )

    # Check rows populated in DB
    history_rows = (
        db.query(PortfolioDailyHistory)
        .filter(PortfolioDailyHistory.user_id == test_user.id)
        .order_by(PortfolioDailyHistory.captured_at.asc())
        .all()
    )
    assert len(history_rows) > 0
    assert history_rows[0].total_cost == 10000.0
    assert history_rows[0].total_value == 10000.0
