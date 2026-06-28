import logging
import re
import functools
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from app.services.portfolio_history_service import portfolio_history_service
from app.services.market_data_service import market_data_service
from app.services.user_service import (
    db_session,
    _load_user_profile,
    _load_watchlist_snapshot,
    _load_portfolio_snapshot,
)
from app.schemas.tool_schemas import (
    ToolResponseEnvelope,
    GetUserProfileInput, UserProfileData,
    GetPortfolioHoldingsInput, PortfolioSnapshotData,
    GetWatchlistInput, WatchlistSnapshotData,
    CalculatorInput, CalculatorData,
    GetPortfolioReturnsHistoryInput, ReturnsHistoryData,
    GetPortfolioRiskMetricsInput, RiskMetricsData,
    GetPortfolioBenchmarkComparisonInput, BenchmarkComparisonData,
    GetAssetCovarianceMatrixInput, CovarianceMatrixData,
    GetHistoricalPerformanceInput, HistoricalPerformanceData,
    GoogleWebSearchInput, GoogleWebSearchData,
    GetTickerDetailsInput, TickerDetailsData,
    GetTickerDetailsBulkInput, TickerDetailsBulkData,
    GetDividendHistoryInput, DividendHistoryData,
    GetDividendHistoryBulkInput, DividendHistoryBulkData,
)

logger = logging.getLogger(__name__)

# ── FIX 5: Cache google_web_search LLM binding at module load ──────────────
# Previously this was re-created inside google_web_search() on every call,
# costing ~1-2s of object construction + an extra nested LLM invocation path.
from app.core.llm import flash_model as _flash_model
_LLM_WITH_SEARCH = _flash_model.bind_tools([{"google_search": {}}])
_LLM_WITH_CALCULATOR = _flash_model.bind_tools([{"code_execution": {}}])


# ── UTILITIES & HELPER FUNCTIONS ───────────────────────────────────────────

def wrap_envelope(data: Any, success: bool = True, source: str = "NiveshIQ") -> dict:
    """Standardized response envelope contract."""
    return {
        "success": success,
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "source": source,
        "data": data,
    }


def validate_tool(input_model, output_model, source_name):
    """
    Decorator that handles input validation, output validation, and wrapping
    the return dictionary in a standardized ToolResponseEnvelope contract.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                validated_input = input_model(**kwargs)
            except Exception as e:
                logger.error(f"Input validation failed for tool {func.__name__}: {e}")
                return wrap_envelope(
                    {"error": f"Input validation failed: {str(e)}"},
                    success=False,
                    source=source_name,
                )
            try:
                raw_data = func(*args, **validated_input.model_dump())
            except Exception as e:
                logger.error(f"Tool execution failed for {func.__name__}: {e}", exc_info=True)
                return wrap_envelope(
                    {"error": f"Tool execution failed: {str(e)}"},
                    success=False,
                    source=source_name,
                )
            try:
                validated_data = output_model(**raw_data)
                return wrap_envelope(
                    validated_data.model_dump(),
                    success=True,
                    source=source_name,
                )
            except Exception as e:
                logger.error(f"Output validation failed for tool {func.__name__}: {e}")
                return wrap_envelope(
                    {"error": f"Output validation failed: {str(e)}"},
                    success=False,
                    source=source_name,
                )
        return wrapper
    return decorator


# ── NATIVE LANGCHAIN @TOOLS DEFINITIONS ────────────────────────────────────

@tool(args_schema=GetUserProfileInput)
@validate_tool(GetUserProfileInput, UserProfileData, "UserProfileService")
def get_user_profile(user_id: str, **kwargs) -> dict:
    """
    Retrieve the user's investment profile including risk appetite, time horizon, goals, monthly budget, and related memory notes.

    Use this tool when:
    - The user asks about their risk profile, risk appetite, or investor type
    - The user wants to know their investment goal, time horizon, or monthly budget
    - The user asks "what do you know about me" regarding investment preferences
    - You need to assess suitability before making a recommendation
    - The user asks about missing fields in their profile

    Returns a dictionary with:
    - full_name: User's full name (nullable)
    - profession: User's profession (nullable)
    - risk_appetite: e.g., "low", "moderate", "high" (nullable)
    - time_horizon: e.g., "short_term", "medium_term", "long_term" (nullable)
    - investment_goal: e.g., "wealth_growth", "retirement", "savings" (nullable)
    - monthly_investment_budget: Monthly amount available for investment (nullable float)
    - missing_fields: List of profile fields the user hasn't filled in yet
    - memory_notes: Relevant remembered context from past conversations (if any)

    Example queries:
    - "What's my risk appetite?"
    - "Show me my investment profile"
    - "How much can I invest per month?"
    - "What are my investment goals?"
    - "Do I have a complete profile?"
    """
    with db_session() as db:
        profile = _load_user_profile(db, user_id)
        profile["memory_notes"] = []
        return profile


@tool(args_schema=GetPortfolioHoldingsInput)
@validate_tool(GetPortfolioHoldingsInput, PortfolioSnapshotData, "HoldingsService")
def get_portfolio_holdings(user_id: str, **kwargs) -> dict:
    """
    Retrieve a comprehensive snapshot of the user's portfolio: summary, top holdings, sector and market cap exposures, concentration warnings, and associated watchlist data.

    Use this tool when:
    - The user asks "what's in my portfolio?" or "show me my holdings"
    - The user wants to know portfolio value, allocation percentages, or sector diversification
    - The user asks about unrealized P&L on their positions
    - You need portfolio data to provide context for another tool (e.g., news, benchmarking)
    - The user asks about concentration risk or portfolio warnings

    Returns a dictionary with:
    - summary: Portfolio-level metrics (total value, total cost, total P&L, total return %, etc.)
    - top_holdings: Up to 5 holdings with symbol, company_name, quantity, avg_buy_price, market_price, market_value, allocation_percent, unrealized_pnl, sector
    - holdings_count: Total number of distinct holdings
    - top_tickers: List of top holding symbols (e.g., ["RELIANCE.NS", "TCS.NS"])
    - sectors: Sorted list of unique sectors present in the portfolio
    - sector_exposure: Dict mapping sector names to allocation percentages
    - market_cap_exposure: Dict mapping market cap categories to allocation percentages

    Example queries:
    - "Show me my portfolio"
    - "What are my top holdings?"
    - "How is my portfolio diversified across sectors?"
    - "What's my unrealized profit and loss?"
    - "Are any of my holdings too concentrated?"
    """
    with db_session() as db:
        return _load_portfolio_snapshot(db, user_id)


@tool(args_schema=GetWatchlistInput)
@validate_tool(GetWatchlistInput, WatchlistSnapshotData, "WatchlistService")
def get_watchlist(user_id: str, **kwargs) -> dict:
    """
    Retrieve the user's watchlist with current market prices and returns since each symbol was added.

    Use this tool when:
    - The user asks "show me my watchlist" or "what am I watching?"
    - The user wants to know how watched stocks have performed since they added them
    - You need to suggest potential investments the user has already shown interest in

    Returns a dictionary with:
    - watchlist: List of items with symbol, company_name, market_price, return_since_added
    - watchlist_symbols: Flat list of ticker symbols in the watchlist
    - watchlist_count: Number of items in the watchlist

    Example queries:
    - "What's on my watchlist?"
    - "Show me my watched stocks"
    - "How have my watchlist stocks performed?"
    """
    with db_session() as db:
        return _load_watchlist_snapshot(db, user_id)


@tool(args_schema=GetHistoricalPerformanceInput)
@validate_tool(GetHistoricalPerformanceInput, HistoricalPerformanceData, "MarketDataService")
def get_historical_performance(
    symbols: List[str],
    start_date: datetime,
    end_date: datetime = datetime.now(timezone.utc),
    **kwargs,
) -> dict:
    """
    Calculate historical return performance for specific stock symbols over a given lookback period.

    Use this tool when:
    - The user asks "how has X performed over the last N days?"
    - You need start and end prices for specific stocks over a date range
    - The user wants to compare performance of multiple stocks
    - You need a sampled price history to show price trends

    Returns a dictionary with:
    - historical_performance: Dict keyed by symbol, each containing:
      - start_date: Beginning date of the period
      - start_price: Price at the start
      - end_date: End date of the period
      - end_price: Price at the end
      - return_percent: Total return % over the period
      - price_history_sample: Sampled prices at regular intervals (up to ~10 data points)

    Example queries:
    - "How has Reliance performed in the last 3 months?"
    - "Compare TCS and Infosys performance over 30 days"
    - "What's the 6-month return for HDFC Bank?"

    Note: Symbols are auto-suffixed with ".NS" for NSE. The price_history_sample provides a sparse representation of the full series.
    """
    return market_data_service.get_historical_performance_bulk(symbols, start_date, end_date)



@tool(args_schema=GetPortfolioReturnsHistoryInput)
@validate_tool(GetPortfolioReturnsHistoryInput, ReturnsHistoryData, "PortfolioHistoryService")
def get_portfolio_returns_history(user_id: str, **kwargs) -> dict:
    """
    Retrieve the user's portfolio value history over time, including cost basis and daily return series.

    Use this tool when:
    - The user asks "how has my portfolio performed over time?" or "show me my returns history"
    - The user wants to see portfolio value on specific dates
    - The user asks "what's my cumulative return?"
    - You need chronological performance data for analysis or visualization

    Returns a dictionary with:
    - dates: List of date strings in chronological order
    - total_values: Portfolio market value at each date
    - total_costs: Total cost basis at each date
    - daily_returns: Daily return percentage for each period
    - cumulative_return_percent: Overall return percentage over the full period

    Example queries:
    - "Show me my portfolio returns over time"
    - "How has my portfolio value changed?"
    - "What's my total return since I started investing?"
    - "Chart my portfolio performance"
    """
    with db_session() as db:
        return portfolio_history_service.get_returns_history(db, user_id)


@tool(args_schema=GetPortfolioRiskMetricsInput)
@validate_tool(GetPortfolioRiskMetricsInput, RiskMetricsData, "PortfolioHistoryService")
def get_portfolio_risk_metrics(user_id: str, **kwargs) -> dict:
    """
    Calculate advanced risk metrics for the user's portfolio: Sharpe ratio, Sortino ratio, volatility, maximum drawdown, and Value-at-Risk (VaR/CVaR).

    Use this tool when:
    - The user asks "what's my portfolio risk?" or "how risky is my portfolio?"
    - The user wants to know Sharpe ratio, Sortino ratio, or other risk-adjusted return metrics
    - The user asks "what's my maximum drawdown?" or "what's the worst-case loss?"
    - You're comparing portfolio risk to a benchmark

    Returns a dictionary with:
    - sharpe_ratio: Risk-adjusted return (risk-free rate adjusted)
    - sortino_ratio: Downside-risk-adjusted return
    - annualized_volatility: Standard deviation of returns (annualized)
    - downside_deviation: Standard deviation of negative returns only
    - max_drawdown: Largest peak-to-trough decline (%)
    - var_95: Value at Risk at 95% confidence (daily loss threshold)
    - var_99: Value at Risk at 99% confidence
    - cvar_95: Conditional VaR (expected shortfall) at 95%
    - cvar_99: Conditional VaR at 99%

    Example queries:
    - "How risky is my portfolio?"
    - "What's my Sharpe ratio?"
    - "What's the maximum drawdown on my portfolio?"
    - "What's the value at risk for my investments?"
    """
    with db_session() as db:
        return portfolio_history_service.calculate_risk_metrics(db, user_id)


@tool(args_schema=GetPortfolioBenchmarkComparisonInput)
@validate_tool(GetPortfolioBenchmarkComparisonInput, BenchmarkComparisonData, "PortfolioHistoryService")
def get_portfolio_benchmark_comparison(user_id: str, **kwargs) -> dict:
    """
    Compare the user's portfolio returns against the Nifty 50 benchmark index to compute Beta, Alpha, Correlation, Tracking Error, and Information Ratio.

    Use this tool when:
    - The user asks "how is my portfolio performing compared to the market?" or "am I beating Nifty?"
    - The user wants to know their portfolio's Beta (market sensitivity)
    - The user asks about Alpha (excess return over benchmark)
    - You need to assess whether the portfolio manager/user is adding value vs passive investing

    Returns a dictionary with:
    - beta: Portfolio sensitivity to market movements (>1 = more volatile than market)
    - alpha_annualized: Annualized excess return over the benchmark
    - correlation: Pearson correlation between portfolio and benchmark returns
    - tracking_error: Standard deviation of the difference between portfolio and benchmark returns
    - information_ratio: Alpha divided by tracking error (risk-adjusted outperformance)

    Example queries:
    - "Am I beating the market?"
    - "What's my portfolio's beta?"
    - "Compare my portfolio to Nifty 50"
    - "What's my alpha?"
    """
    with db_session() as db:
        return portfolio_history_service.compare_to_benchmark(db, user_id)


@tool(args_schema=GetAssetCovarianceMatrixInput)
@validate_tool(GetAssetCovarianceMatrixInput, CovarianceMatrixData, "PortfolioHistoryService")
def get_asset_covariance_matrix(user_id: str, **kwargs) -> dict:
    """
    Calculate the annualized covariance and correlation matrices for all active holdings in the user's portfolio.

    Use this tool when:
    - The user asks about diversification benefits or "how do my stocks move together?"
    - You need to understand which holdings are correlated (redundant risk)
    - The user wants to optimize their portfolio allocation
    - Advanced risk analysis requiring covariance between assets

    Returns a dictionary with:
    - symbols: List of holding symbols corresponding to matrix rows/columns
    - covariance_matrix: 2D list of annualized covariance values between each pair of assets
    - correlation_matrix: 2D list of correlation coefficients (ranges from -1 to 1) between each pair

    Example queries:
    - "How correlated are my holdings?"
    - "Show me the covariance matrix of my portfolio"
    - "Which of my stocks move together?"
    - "Are my holdings properly diversified?"
    """
    with db_session() as db:
        return portfolio_history_service.calculate_asset_covariance(db, user_id)


@tool(args_schema=GoogleWebSearchInput)
@validate_tool(GoogleWebSearchInput, GoogleWebSearchData, "GoogleSearchService")
def google_web_search(query: str, **kwargs) -> dict:
    """
    Search Google for real-time web results, macro trends, geopolitical events, news, or general knowledge.
    Always fetch the latest information (current date) from the web when the user asks about current events, news, or market-moving announcements.

    Use this tool when:
    - You need current market events, news, or announcements not available in other database tools
    - The user asks general market/macro questions or for recent news
    - The user asks "any news about my portfolio?" or "what's affecting my investments?"
    - You need to search the web to answer the query

    Examples:
    - "What's the latest news on Reliance Industries?"
    - "Any news about the IT sector today?"
    - "Why is the market down today?"
    - "What did the RBI announce?"
    - "What news is relevant to my portfolio today?"
    - "Any earnings reports for my holdings?"
    - "What's the market news affecting my stocks?"
    - "What's happening in the world today that could impact markets?"
    - "Does any of my stocks in my portfolio announced dividends or earnings today?"
    """
    res = _LLM_WITH_SEARCH.invoke([HumanMessage(content=query)])
    return {"query": query, "result": res.content}


def normalize_ticker_symbol(symbol: str) -> str:
    symbol = symbol.upper().strip()
    if symbol and "." not in symbol:
        return f"{symbol}.NS"
    return symbol


@tool(args_schema=GetTickerDetailsInput)
@validate_tool(GetTickerDetailsInput, TickerDetailsData, "MarketDataService")
def get_ticker_details(symbol: str, **kwargs) -> dict:
    """
    Retrieve market price, financial and valuation metrics for a specific stock ticker.

    Use this tool when:
    - The user asks "what's the price of X?" or "show me details for Y"
    - The user asks for PE ratio, EPS, beta, market cap, industry, day highs/lows, 52-week ranges, open, previous close, or volume of a stock.
    - You need deep stock-level valuation metrics to perform investment analysis.

    Returns a dictionary with:
    - symbol: The ticker symbol queried (auto-suffixed with .NS)
    - fetched_at: Timestamp of when the data was fetched (ISO-8601 format)
    - price: Current market price of the stock
    - market_cap: Market capitalization of the company
    - company_name: Full name of the company
    - sector: Sector of the company
    - industry: Industry of the company
    - beta: Beta coefficient of the stock
    - trailing_pe: Trailing Price-to-Earnings ratio
    - forward_pe: Forward Price-to-Earnings ratio
    - eps_trailing_twelve_months: Trailing twelve months Earnings Per Share
    - eps_forward: Forward Earnings Per Share
    - 52w_low: 52-week low price
    - 52w_high: 52-week high price
    - day_low: Low price of the current trading day
    - day_high: High price of the current trading day
    - open: Opening price of the current trading day
    - previous_close: Previous trading day's closing price
    - volume: Trading volume of the current trading day
    """
    sym = normalize_ticker_symbol(symbol)
    return market_data_service.fetch_ticker_data(sym)


@tool(args_schema=GetTickerDetailsBulkInput)
@validate_tool(GetTickerDetailsBulkInput, TickerDetailsBulkData, "MarketDataService")
def get_ticker_details_bulk(symbols: list[str], **kwargs) -> dict:
    """
    Retrieve market price, financial and valuation metrics for a list of stock tickers in bulk (using parallel workers).

    Use this tool when:
    - The user asks "show me details for my portfolio holdings" or "get metrics for these stocks"
    - The user asks for valuation/details for multiple stocks or a whole list.
    - You need to fetch stock-level metrics for multiple tickers efficiently.

    Returns a dictionary with:
    - ticker_details: Dict mapping each symbol (auto-suffixed with .NS) to its corresponding TickerDetailsData object containing:
      - symbol: The ticker symbol queried
      - fetched_at: Timestamp of when the data was fetched (ISO-8601 format)
      - price: Current market price of the stock
      - market_cap: Market capitalization of the company
      - company_name: Full name of the company
      - sector: Sector of the company
      - industry: Industry of the company
      - beta: Beta coefficient of the stock
      - trailing_pe: Trailing Price-to-Earnings ratio
      - forward_pe: Forward Price-to-Earnings ratio
      - eps_trailing_twelve_months: Trailing twelve months Earnings Per Share
      - eps_forward: Forward Earnings Per Share
      - 52w_low: 52-week low price
      - 52w_high: 52-week high price
      - day_low: Low price of the current trading day
      - day_high: High price of the current trading day
      - open: Opening price of the current trading day
      - previous_close: Previous trading day's closing price
      - volume: Trading volume of the current trading day
    """
    normalized_symbols = [normalize_ticker_symbol(s) for s in symbols if s.strip()]
    res = market_data_service.fetch_ticker_data_bulk(normalized_symbols)
    return {"ticker_details": res}


@tool(args_schema=GetDividendHistoryInput)
@validate_tool(GetDividendHistoryInput, DividendHistoryData, "MarketDataService")
def get_dividend(symbol: str, **kwargs) -> dict:
    """
    Retrieve recent and historical dividend payments for a stock over the past 5 years.

    Use this tool when:
    - The user asks "What dividends has X announced?"
    - The user asks "what dividends has X paid?" or "what is the dividend history of X?"
    - The user asks about dividend payouts, yields, history, or payout dates for a stock.
    - You need to calculate dividend yield or assess a stock's dividend track record.

    Returns a dictionary with:
    - symbol: The ticker symbol queried (auto-suffixed with .NS)
    - dividends: List of DividendRecord objects, each containing:
      - date: Ex/declaration date of the dividend (string)
      - dividend: Dividend amount per share (float)

    Example queries:
    - "What dividends has been announced by TCS?"
    - "What dividends has ITC paid in the last 5 years?"
    - "Show me the dividend history of Reliance"
    - "Has TCS declared any dividends recently?"

    Note: Data covers the past 5 years. The symbol is auto-suffixed with ".NS" for NSE if no exchange suffix is provided.
    """
    sym = normalize_ticker_symbol(symbol)
    divs = market_data_service.get_dividend(sym)
    return {"symbol": sym, "dividends": divs}


@tool(args_schema=GetDividendHistoryBulkInput)
@validate_tool(GetDividendHistoryBulkInput, DividendHistoryBulkData, "MarketDataService")
def get_dividend_bulk(symbols: list[str], **kwargs) -> dict:
    """
    Retrieve recent and historical dividend payments for a list of stock tickers in bulk over the past 5 years.

    Use this tool when:
    - The user asks for dividend history of multiple stocks or their entire portfolio.
    - You need to compare dividend track records across several stocks at once.
    - The user asks "what dividends have my holdings paid?"
    - The user asks "what dividends has multiple companies announced?"

    Returns a dictionary with:
    - dividends: Dict mapping each symbol (auto-suffixed with .NS) to a list of DividendRecord objects, each containing:
      - date: Ex/declaration date of the dividend (string)
      - dividend: Dividend amount per share (float)

    Example queries:
    - "Show me dividend history for all my portfolio holdings"
    - "Compare dividends paid by ITC, HUL, and HDFC Bank"
    """
    normalized_symbols = [normalize_ticker_symbol(s) for s in symbols if s.strip()]
    divs_map = market_data_service.get_dividend_bulk(normalized_symbols)
    return {"dividends": divs_map}

@tool(args_schema=CalculatorInput)
@validate_tool(CalculatorInput, CalculatorData, "CalculatorService")
def calculator(expression: str, **kwargs) -> dict:
    """
    Execute mathematical expressions and precise numerical calculations.

    Use this tool when:
    - You need to compute exact mathematical operations (addition, subtraction, multiplication, division).
    - The user asks for compound interest, portfolio returns, or financial metric calculations.
    - Resolving complex algebraic, logarithmic, or trigonometric formulas.
    - Balancing financial portfolios, counting asset allocations, or determining percentage changes.

    Examples:
    - "Calculate the compound interest on $10,000 at 5% for 3 years."
    - "What is the total value of 50 shares of Apple at $175 plus 20 shares of Microsoft at $400?"
    - "What is the square root of 144 multiplied by 15?"
    - "Compute the standard deviation for the following stock returns: [0.02, -0.01, 0.05, 0.03]."
    """
    res = _LLM_WITH_CALCULATOR.invoke([HumanMessage(content=expression)])
    content = res.content
    if isinstance(content, list):
        texts = []

        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    texts.append(part.get("text", ""))

        content = "\n".join(texts)
    return {"expression": expression, "result": content}


# ── TOOLS REGISTRY EXPORT ──────────────────────────────────────────────────

TOOLS = [
    get_user_profile,
    get_portfolio_holdings,
    get_watchlist,
    calculator,
    get_portfolio_returns_history,
    get_portfolio_risk_metrics,
    get_portfolio_benchmark_comparison,
    get_asset_covariance_matrix,
    get_historical_performance,
    google_web_search,
    get_ticker_details,
    get_ticker_details_bulk,
    get_dividend,
    get_dividend_bulk,
]
