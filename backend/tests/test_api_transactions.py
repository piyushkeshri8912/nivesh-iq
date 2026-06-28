import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.transaction import Transaction
from app.models.user import User

@pytest.fixture(autouse=True)
def mock_external_services(mocker):
    # Mock external calls to avoid side effects
    mock_rebuild = mocker.patch("app.services.portfolio_history_service.portfolio_history_service.rebuild_history")
    mock_company_name = mocker.patch("app.services.market_data_service.market_data_service.get_company_name")
    mock_company_name.return_value = "Mock Company Ltd"
    
    # Mock LLM for the file upload route
    mock_mapping = mocker.MagicMock()
    mock_mapping.content = '{"symbol": "Symbol", "transaction_type": "Type", "quantity": "Quantity", "price": "Price", "total_value": null, "executed_at": "Date", "fees": null}'
    mocker.patch("app.core.llm.flash_lite_model.invoke", return_value=mock_mapping)

    return {
        "rebuild_history": mock_rebuild,
        "get_company_name": mock_company_name
    }

def test_get_transactions_empty(client: TestClient, auth_headers: dict, test_user: User):
    response = client.get("/api/v1/transactions", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []

def test_create_transaction_success(client: TestClient, auth_headers: dict, test_user: User, db: Session):
    payload = {
        "symbol": "INFY",
        "transaction_type": "BUY",
        "quantity": 10.0,
        "price": 1500.00,
        "fees": 20.0,
        "executed_at": datetime.now(timezone.utc).isoformat()
    }
    response = client.post("/api/v1/transactions", json=payload, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "INFY.NS"
    assert data["company_name"] == "Mock Company Ltd"
    assert data["quantity"] == 10.0
    assert data["price"] == 1500.0

    # Verify database state
    db_tx = db.query(Transaction).filter(Transaction.user_id == test_user.id).first()
    assert db_tx is not None
    assert db_tx.symbol == "INFY.NS"

def test_create_transaction_invalid_data(client: TestClient, auth_headers: dict):
    # Future execution date validation (more than 24 hours in the future)
    future_date = (datetime.now() + timedelta(days=2)).isoformat()
    payload = {
        "symbol": "INFY",
        "transaction_type": "BUY",
        "quantity": 10.0,
        "price": 1500.00,
        "executed_at": future_date
    }
    response = client.post("/api/v1/transactions", json=payload, headers=auth_headers)
    assert response.status_code == 422
    
    # Negative quantity
    payload["executed_at"] = datetime.now().isoformat()
    payload["quantity"] = -5.0
    response = client.post("/api/v1/transactions", json=payload, headers=auth_headers)
    assert response.status_code == 422

def test_update_transaction_success(client: TestClient, auth_headers: dict, test_user: User, db: Session):
    # Setup test transaction
    tx = Transaction(
        user_id=test_user.id,
        symbol="TCS.NS",
        company_name="TCS",
        transaction_type="BUY",
        quantity=5,
        price=3000.0,
        fees=10.0,
        executed_at=datetime.now()
    )
    db.add(tx)
    db.commit()

    update_payload = {
        "quantity": 8.0,
        "price": 3100.0
    }
    response = client.put(f"/api/v1/transactions/{tx.id}", json=update_payload, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["quantity"] == 8.0
    assert data["price"] == 3100.0

def test_delete_transaction_success(client: TestClient, auth_headers: dict, test_user: User, db: Session):
    tx = Transaction(
        user_id=test_user.id,
        symbol="TCS.NS",
        company_name="TCS",
        transaction_type="BUY",
        quantity=5,
        price=3000.0,
        fees=10.0,
        executed_at=datetime.now()
    )
    db.add(tx)
    db.commit()

    response = client.delete(f"/api/v1/transactions/{tx.id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["message"] == "Transaction deleted successfully"

    # Assert deleted from DB
    assert db.query(Transaction).filter(Transaction.id == tx.id).first() is None

def test_upload_trades_success(client: TestClient, auth_headers: dict, test_user: User, db: Session):
    csv_content = (
        "Symbol,Type,Quantity,Price,Date\n"
        "RELIANCE,BUY,10,2500.00,2026-06-22\n"
    )
    files = {"file": ("trades.csv", csv_content.encode("utf-8"), "text/csv")}
    response = client.post("/api/v1/transactions/upload", files=files, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["imported"] == 1
    assert data["duplicates"] == 0

    # Duplicate check on re-upload
    response_dup = client.post("/api/v1/transactions/upload", files=files, headers=auth_headers)
    assert response_dup.status_code == 200
    data_dup = response_dup.json()
    assert data_dup["imported"] == 0
    assert data_dup["duplicates"] == 1
