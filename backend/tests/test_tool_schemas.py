import pytest
from pydantic import ValidationError
from app.schemas.tool_schemas import (
    GetTickerDetailsInput,
    TickerDetailsData,
    GetDividendHistoryInput,
    DividendRecord,
    DividendHistoryData
)
from app.services.tools import validate_tool, wrap_envelope

def test_ticker_details_input_validation():
    # Valid input
    inp = GetTickerDetailsInput(symbol="RELIANCE.NS")
    assert inp.symbol == "RELIANCE.NS"

    # Missing symbol (Validation Error)
    with pytest.raises(ValidationError):
        GetTickerDetailsInput()

def test_ticker_details_output_validation():
    # Valid output structure
    valid_data = {
        "symbol": "TCS.NS",
        "fetched_at": "2026-06-22T21:19:33.582567+00:00",
        "price": 2127.8,
        "market_cap": 7698566348800.0,
        "company_name": "Tata Consultancy Services Limited",
        "sector": "Technology",
        "industry": "Information Technology Services",
        "beta": 0.227,
        "trailing_pe": 15.645589,
        "52w_low": 2059.9,
        "52w_high": 3489.9
    }
    details = TickerDetailsData(**valid_data)
    assert details.symbol == "TCS.NS"
    assert details.fifty_two_week_low == 2059.9  # check field alias matching

def test_dividend_history_schemas():
    record = DividendRecord(date="2026-02-04", dividend=6.5)
    assert record.dividend == 6.5

    div_history = DividendHistoryData(
        symbol="ITC.NS",
        dividends=[record]
    )
    assert len(div_history.dividends) == 1
    assert div_history.dividends[0].date == "2026-02-04"

def test_validate_tool_decorator():
    # Setup dummy schemas for decorator test
    class DummyInput(GetTickerDetailsInput):
        pass

    class DummyOutput(TickerDetailsData):
        pass

    # Create dummy tool function
    @validate_tool(DummyInput, DummyOutput, "DummyService")
    def my_dummy_tool(symbol: str, **kwargs):
        return {
            "symbol": symbol,
            "fetched_at": "2026-06-22T00:00:00",
            "price": 100.0
        }

    # Test success flow
    res = my_dummy_tool(symbol="RELIANCE.NS")
    assert res["success"] is True
    assert res["data"]["symbol"] == "RELIANCE.NS"
    assert res["data"]["price"] == 100.0

    # Test output validation failure flow (price is string instead of float, but Pydantic will try to cast. Let's send an invalid type that fails validation, like price=None)
    @validate_tool(DummyInput, DummyOutput, "DummyService")
    def failing_output_tool(symbol: str, **kwargs):
        return {
            "symbol": symbol,
            "fetched_at": "2026-06-22T00:00:00",
            "price": "not-a-float"
        }
        
    res_fail = failing_output_tool(symbol="RELIANCE.NS")
    assert res_fail["success"] is False
    assert "error" in res_fail["data"]
