import pytest
import io
import pandas as pd
from app.services.trade_upload_service import (
    _normalise_type,
    _normalise_symbol,
    _normalise_date,
    _normalise_float,
    _find_header_row,
    parse_trade_file,
    extract_trades
)

def test_normalise_type():
    assert _normalise_type("BUY") == "BUY"
    assert _normalise_type("B") == "BUY"
    assert _normalise_type("purchase") == "BUY"
    assert _normalise_type("1") == "BUY"
    
    assert _normalise_type("SELL") == "SELL"
    assert _normalise_type("S") == "SELL"
    assert _normalise_type("sale") == "SELL"
    assert _normalise_type("-1") == "SELL"
    
    # Defaults to BUY for unknown values
    assert _normalise_type("HOLD") == "BUY"
    assert _normalise_type(None) == "BUY"

def test_normalise_symbol():
    assert _normalise_symbol("infy") == "INFY"
    assert _normalise_symbol("  RELIANCE  ") == "RELIANCE"
    assert _normalise_symbol(None) is None
    assert _normalise_symbol(float('nan')) is None

def test_normalise_date():
    assert _normalise_date("2026-06-22") == "2026-06-22T00:00:00+00:00"
    assert _normalise_date("22-06-2026") == "2026-06-22T00:00:00+00:00"
    assert _normalise_date("22/06/2026") == "2026-06-22T00:00:00+00:00"
    assert _normalise_date("22-Jun-2026") == "2026-06-22T00:00:00+00:00"
    assert _normalise_date("22-06-2026 10:30 AM") == "2026-06-22T10:30:00+00:00"
    assert _normalise_date("invalid-date") is None
    assert _normalise_date(None) is None

def test_normalise_float():
    assert _normalise_float("123.45") == 123.45
    assert _normalise_float("1,234.50") == 1234.50
    assert _normalise_float("₹12,345.67") == 12345.67
    assert _normalise_float("  $100.00  ") == 100.00
    assert _normalise_float("invalid-float") is None
    assert _normalise_float(None) is None

def test_find_header_row():
    # Grid of rows: metadata header rows before real data
    data = [
        ["Report Metadata", "", "", ""],
        ["User: John Doe", "", "", ""],
        ["Symbol", "Type", "Quantity", "Price"],  # Real header at index 2
        ["INFY", "BUY", "10", "1500.00"],
    ]
    df = pd.DataFrame(data)
    assert _find_header_row(df) == 2

    # Standard clean file
    data_clean = [
        ["Symbol", "Qty", "Action", "Rate"],
        ["TCS", "5", "SELL", "3200.00"],
    ]
    df_clean = pd.DataFrame(data_clean)
    assert _find_header_row(df_clean) == 0

def test_parse_trade_file():
    csv_content = (
        "Groww Trade History,,,,\n"
        "Date: 2026-06-22,,,,\n"
        "Symbol,Type,Quantity,Price,Date\n"
        "RELIANCE,BUY,5,2400.00,2026-06-22\n"
    )
    df = parse_trade_file(csv_content.encode("utf-8"), "trades.csv")
    assert len(df) == 1
    assert list(df.columns) == ["Symbol", "Type", "Quantity", "Price", "Date"]
    assert df.iloc[0]["Symbol"] == "RELIANCE"

def test_extract_trades_derived_price(mocker):
    # Test case where price column is missing but total_value is present
    mock_mapping = mocker.MagicMock()
    mock_mapping.content = '{"symbol": "Symbol", "transaction_type": "Type", "quantity": "Quantity", "price": null, "total_value": "TotalValue", "executed_at": "Date", "fees": null}'
    mocker.patch("app.core.llm.flash_lite_model.invoke", return_value=mock_mapping)

    csv_content = (
        "Symbol,Type,Quantity,TotalValue,Date\n"
        "INFY,BUY,10,15000.00,2026-06-22\n"
    )
    trades, errors = extract_trades(csv_content.encode("utf-8"), "trades.csv")
    assert len(trades) == 1
    assert len(errors) == 0
    trade = trades[0]
    assert trade["symbol"] == "INFY"
    # Derived price: 15000.00 / 10 = 1500.0
    assert trade["price"] == 1500.0
