from datetime import datetime, timezone, timezone

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

# Standard Envelope Model
class ToolResponseEnvelope(BaseModel):
    success: bool = Field(description="Indicates if the tool run was successful")
    timestamp: str = Field(description="ISO-8601 timestamp of tool execution")
    source: str = Field(description="Data source provider name")
    data: Any = Field(description="The validated payload of the tool")

# 1. User Profile
class GetUserProfileInput(BaseModel):
    user_id: str = Field(description="The unique UUID of the user")

class UserProfileData(BaseModel):
    full_name: Optional[str] = None
    profession: Optional[str] = None
    risk_appetite: Optional[str] = None
    time_horizon: Optional[str] = None
    investment_goal: Optional[str] = None
    monthly_investment_budget: Optional[float] = None
    missing_fields: List[str] = Field(default_factory=list)
    memory_notes: List[str] = Field(default_factory=list)


# 2. Portfolio Holdings
class GetPortfolioHoldingsInput(BaseModel):
    user_id: str = Field(description="The unique UUID of the user")

class HoldingItem(BaseModel):
    symbol: str
    company_name: str
    quantity: float
    average_buy_price: float
    market_price: float
    market_value: float
    allocation_percent: float
    unrealized_pnl: float
    sector: str

class PortfolioSnapshotData(BaseModel):
    summary: Dict[str, Any]
    top_holdings: List[HoldingItem]
    holdings_count: int
    top_tickers: List[str]
    sectors: List[str]
    sector_exposure: List[Dict[str, Any]] = Field(default_factory=list)
    market_cap_exposure: List[Dict[str, Any]] = Field(default_factory=list)


# 3. Watchlist
class GetWatchlistInput(BaseModel):
    user_id: str = Field(description="The unique UUID of the user")

class WatchlistItemSchema(BaseModel):
    symbol: str
    company_name: str
    market_price: float
    return_since_added: float

class WatchlistSnapshotData(BaseModel):
    watchlist: List[WatchlistItemSchema]
    watchlist_symbols: List[str]
    watchlist_count: int

# 4. Market Data
class GetMarketDataInput(BaseModel):
    symbols: List[str] = Field(description="The ticker symbols to query")

class MarketSnapshotData(BaseModel):
    market_data: List[Dict[str, Any]] = Field(default_factory=list)


# 5. Portfolio Returns History
class GetPortfolioReturnsHistoryInput(BaseModel):
    user_id: str = Field(description="The unique UUID of the user")

class ReturnsHistoryData(BaseModel):
    dates: List[str] = Field(default_factory=list)
    total_values: List[float] = Field(default_factory=list)
    total_costs: List[float] = Field(default_factory=list)
    daily_returns: List[float] = Field(default_factory=list)
    cumulative_return_percent: float

# 6. Portfolio Risk Metrics
class GetPortfolioRiskMetricsInput(BaseModel):
    user_id: str = Field(description="The unique UUID of the user")

class RiskMetricsData(BaseModel):
    sharpe_ratio: float
    sortino_ratio: float
    annualized_volatility: float
    downside_deviation: float
    max_drawdown: float
    var_95: float
    var_99: float
    cvar_95: float
    cvar_99: float

# 7. Portfolio Benchmark Comparison
class GetPortfolioBenchmarkComparisonInput(BaseModel):
    user_id: str = Field(description="The unique UUID of the user")

class BenchmarkComparisonData(BaseModel):
    beta: float
    alpha_annualized: float
    correlation: float
    tracking_error: float
    information_ratio: float

# 8. Asset Covariance Matrix
class GetAssetCovarianceMatrixInput(BaseModel):
    user_id: str = Field(description="The unique UUID of the user")

class CovarianceMatrixData(BaseModel):
    symbols: List[str]
    covariance_matrix: List[List[float]]
    correlation_matrix: List[List[float]]

# 9. Historical Performance
class GetHistoricalPerformanceInput(BaseModel):
    symbols: List[str] = Field(description="List of ticker symbols to check performance for")
    start_date: datetime = Field(description="Start date for historical performance analysis (ISO-8601 format)")
    end_date: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc), description="End date for historical performance analysis (ISO-8601 format, defaults to now)")

class HistoricalPerformanceItem(BaseModel):
    start_date: str
    start_price: float
    end_date: str
    end_price: float
    return_percent: float
    price_history_sample: Dict[str, float]

class HistoricalPerformanceData(BaseModel):
    historical_performance: Dict[str, Any]


# 10. Google Web Search
class GoogleWebSearchInput(BaseModel):
    query: str = Field(description="The query string to search Google for")

class GoogleWebSearchData(BaseModel):
    query: str
    result: str


# 11. Ticker Details (Single & Bulk)
class GetTickerDetailsInput(BaseModel):
    symbol: str = Field(description="The ticker symbol to query detailed metrics for (e.g. RELIANCE.NS)")

class TickerDetailsData(BaseModel):
    symbol: str
    fetched_at: str
    price: Optional[float] = None
    market_cap: Optional[float] = None
    company_name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    beta: Optional[float] = None
    trailing_pe: Optional[float] = None
    forward_pe: Optional[float] = None
    eps_trailing_twelve_months: Optional[float] = None
    eps_forward: Optional[float] = None
    fifty_two_week_low: Optional[float] = Field(None, alias="52w_low")
    fifty_two_week_high: Optional[float] = Field(None, alias="52w_high")
    day_low: Optional[float] = None
    day_high: Optional[float] = None
    open: Optional[float] = None
    previous_close: Optional[float] = None
    volume: Optional[float] = None

    class Config:
        populate_by_name = True

class GetTickerDetailsBulkInput(BaseModel):
    symbols: List[str] = Field(description="List of ticker symbols to query detailed metrics for")

class TickerDetailsBulkData(BaseModel):
    ticker_details: Dict[str, Any] = Field(description="Map of symbol to ticker details/metrics")


# 12. Dividend History (Single & Bulk)
class GetDividendHistoryInput(BaseModel):
    symbol: str = Field(description="The ticker symbol to query dividend history for (e.g. ITC.NS)")

class DividendRecord(BaseModel):
    date: str
    dividend: float

class DividendHistoryData(BaseModel):
    symbol: str
    dividends: List[DividendRecord] = Field(default_factory=list)

class GetDividendHistoryBulkInput(BaseModel):
    symbols: List[str] = Field(description="List of ticker symbols to query dividend histories for")

class DividendHistoryBulkData(BaseModel):
    dividends: Dict[str, List[DividendRecord]] = Field(description="Map of symbol to list of dividend records")

# 13. Python Code Execution (Calculator)
class CalculatorInput(BaseModel):
    expression: str = Field(description="The mathematical, financial, or logical problem that requires Python code execution to solve")

class CalculatorData(BaseModel):
    expression: str
    result: str