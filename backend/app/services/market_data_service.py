import concurrent.futures
import logging
import threading
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from typing import Any

import pandas as pd
import yfinance as yf
from sqlalchemy.orm import Session

from app.core.cache import cache_manager
from app.db.session import SessionLocal
from app.models.market_price import MarketPrice

logger = logging.getLogger(__name__)


class MarketDataNotFoundError(Exception):
    """Raised when market data cannot be resolved from cache, API, or database fallback."""
    pass


def classify_asset(name: str) -> str:
    """Classify asset type based on fund/company name when sector is unavailable."""
    if not name:
        return "Other"
    n = name.lower()
    if "gold" in n:
        return "Gold"
    if "silver" in n:
        return "Silver"
    if "etf" in n:
        return "ETF"
    return "Equity"


def retry_with_backoff(max_attempts: int = 3, backoff_factor: float = 2.0):
    """Decorator that retries the wrapped function with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exception = exc
                    if attempt < max_attempts - 1:
                        sleep_time = backoff_factor * (2 ** attempt)
                        logger.warning(
                            "%s failed (attempt %d/%d). Retrying in %.2fs. Error: %s",
                            func.__name__, attempt + 1, max_attempts, sleep_time, exc,
                        )
                        time.sleep(sleep_time)
                    else:
                        logger.error(
                            "%s failed after %d attempts.",
                            func.__name__, max_attempts,
                        )
            raise last_exception
        return wrapper
    return decorator


class MarketDataService:
    PRICE_TTL = 300
    NAME_TTL = 31_536_000
    SECTOR_TTL = 31_536_000

    METADATA_FIELDS = (
        "price",
        "company_name",
        "sector",
    )

    def __init__(self):
        # Thread locks to prevent parallel thundering herds during cache/DB misses
        self._fetch_lock = threading.Lock()
        self._bulk_price_lock = threading.Lock()
        self._metadata_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Internal cache / DB helpers
    # ------------------------------------------------------------------

    def _get_cached_field(self, symbol: str, field: str):
        """Return cached value for a given field key."""
        return cache_manager.get(f"market_data:{field}:{symbol}")

    def _set_cached_field(self, symbol: str, field: str, value, ttl: int) -> None:
        cache_manager.set(f"market_data:{field}:{symbol}", value, ttl=ttl)

    def _set_cache_field_if_not_none(self, symbol: str, field: str, value, ttl: int) -> None:
        if value is not None:
            self._set_cached_field(symbol, field, value, ttl)

    def _all_metadata_cached(self, symbol: str) -> bool:
        return all(self._get_cached_field(symbol, f) is not None for f in ("price", "name", "sector"))

    def _cached_metadata(self, symbol: str) -> dict[str, Any]:
        return {
            "price": float(self._get_cached_field(symbol, "price")),
            "company_name": str(self._get_cached_field(symbol, "name")),
            "sector": str(self._get_cached_field(symbol, "sector")),
        }

    def _metadata_from_row(self, row: "MarketPrice") -> dict[str, Any]:
        return {
            "price": row.price,
            "company_name": row.company_name,
            "sector": row.sector,
        }

    def _cache_metadata(self, symbol: str, data: dict[str, Any]) -> None:
        """Write all metadata fields to cache using a single source of truth."""
        self._set_cache_field_if_not_none(symbol, "price", data.get("price"), self.PRICE_TTL)
        self._set_cache_field_if_not_none(symbol, "name", data.get("company_name"), self.NAME_TTL)
        self._set_cache_field_if_not_none(symbol, "sector", data.get("sector"), self.SECTOR_TTL)

    def _warm_cache_from_row(self, symbol: str, row: "MarketPrice") -> None:
        """Populate all cache keys from a MarketPrice DB row."""
        self._cache_metadata(symbol, self._metadata_from_row(row))

    def _read_db_row(self, symbol: str, db: Session = None) -> "MarketPrice | None":
        """Return a single MarketPrice row using an external or local session."""
        if db:
            return db.query(MarketPrice).filter(MarketPrice.symbol == symbol).first()
        with self._get_db() as local_db:
            return local_db.query(MarketPrice).filter(MarketPrice.symbol == symbol).first()

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        return symbol.upper().strip()

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    @contextmanager
    def _get_db(self):
        """Context manager to ensure safe DB session allocation and cleanup."""
        db = SessionLocal()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Database save helpers
    # ------------------------------------------------------------------

    def _save_market_price_to_db(
        self,
        symbol: str,
        price: float,
        company_name: str = None,
        sector: str = None,
        market_cap: float = None,
    ) -> None:
        """Saves a single market price entry to database."""
        self._save_market_prices_bulk_to_db({
            symbol: {
                "price": price,
                "company_name": company_name,
                "sector": sector,
                "market_cap": market_cap,
            }
        })

    def _save_market_prices_bulk_to_db(
        self, updates: dict[str, dict[str, Any]], db: Session = None
    ) -> None:
        """
        Saves or updates market prices and metadata in the database in bulk.
        If a db session is provided, it will be used (caller manages commit/rollback).
        Otherwise a new session is created and managed internally.
        """
        if not updates:
            return

        normalized_updates = {self._normalize_symbol(s): data for s, data in updates.items()}
        now_utc = self._utcnow()

        logger.info("[DB] Bulk persisting prices & metadata for %d symbols", len(normalized_updates))
        try:
            if db is None:
                with self._get_db() as local_db:
                    self._do_bulk_save(local_db, normalized_updates, now_utc)
            else:
                self._do_bulk_save(db, normalized_updates, now_utc)
        except Exception as e:
            logger.exception("Error during bulk saving of market prices: %s", e)

    def _do_bulk_save(self, db: Session, updates: dict[str, dict[str, Any]], now_utc: datetime) -> None:
        """Internal bulk save using an open session."""
        rows = db.query(MarketPrice).filter(MarketPrice.symbol.in_(updates.keys())).all()
        existing_map = {row.symbol: row for row in rows}

        for symbol, data in updates.items():
            row = existing_map.get(symbol)
            if row:
                for field, attr in (
                    ("price", "price"),
                    ("company_name", "company_name"),
                    ("sector", "sector"),
                    ("market_cap", "market_cap"),
                ):
                    value = data.get(field)
                    if value is not None:
                        setattr(row, attr, value)
                row.updated_at = now_utc
            else:
                db.add(
                    MarketPrice(
                        symbol=symbol,
                        price=data.get("price") if data.get("price") is not None else 0.0,
                        company_name=data.get("company_name"),
                        sector=data.get("sector"),
                        market_cap=data.get("market_cap"),
                        updated_at=now_utc,
                    )
                )

    # ------------------------------------------------------------------
    # yfinance helpers
    # ------------------------------------------------------------------

    def _get_fast_info(self, ticker: yf.Ticker) -> dict[str, Any]:
        """Wrapper to access fast_info safely across yfinance versions."""
        try:
            if hasattr(ticker, "get_fast_info"):
                return ticker.get_fast_info() or {}
            return dict(ticker.fast_info or {})
        except Exception:
            return {}

    @retry_with_backoff(max_attempts=3, backoff_factor=2.0)
    def _download_yfinance(self, **kwargs):
        """Unified yfinance.download wrapper with retries."""
        data = yf.download(progress=False, **kwargs)
        if data is None or data.empty:
            raise ValueError("yfinance download returned empty dataset.")
        return data

    def _extract_latest_close(self, data, symbol: str, multi_symbol: bool) -> float | None:
        """Extract the latest close from yf.download output."""
        try:
            td = data[symbol] if multi_symbol else data
            if td is None or td.empty:
                return None
            close_col = "Close" if "Close" in td.columns else ("Adj Close" if "Adj Close" in td.columns else None)
            if close_col is None:
                return None
            series = td[close_col].dropna()
            if series.empty:
                return None
            value = series.iloc[-1]
            return float(value) if value and value > 0 else None
        except Exception:
            return None

    @retry_with_backoff(max_attempts=3, backoff_factor=2.0)
    def _fetch_yfinance_metadata(self, symbol: str) -> dict[str, Any]:
        """
        Fetch comprehensive market data from yfinance.
        Raises an exception if the data cannot be resolved after retries.
        """
        ticker = yf.Ticker(symbol)
        fast_info = self._get_fast_info(ticker)
        info = ticker.info or {}

        price_val = (
            fast_info.get("lastPrice")
            or fast_info.get("last_price")
            or info.get("regularMarketPrice")
            or info.get("currentPrice")
        )
        if price_val is None:
            history = ticker.history(period="1d")
            if not history.empty:
                price_val = history["Close"].dropna().iloc[-1]

        if price_val is None or price_val <= 0:
            raise ValueError(f"No valid price resolved from yfinance for {symbol}")

        price = float(price_val)

        name = info.get("longName") or info.get("shortName") or symbol
        y_sector = info.get("sector")
        if not y_sector or str(y_sector).strip().lower() in ("other", "none", "n/a", ""):
            sector = classify_asset(name)
        else:
            sector = str(y_sector)

        return {
            "price": price,
            "company_name": str(name),
            "sector": str(sector),
        }

    def _resolve_and_update(self, symbol: str) -> dict[str, Any]:
        """
        Coordinates the core Cache -> yfinance -> DB fallback hierarchy.
        Raises MarketDataNotFoundError if data cannot be resolved at all.
        """
        symbol = self._normalize_symbol(symbol)

        try:
            data = self._fetch_yfinance_metadata(symbol)
            self._save_market_price_to_db(
                symbol,
                price=data["price"],
                company_name=data["company_name"],
                sector=data["sector"],
                market_cap=None,
                fifty_two_week_low=None,
                fifty_two_week_high=None,
                day_low=None,
                day_high=None,
            )
            self._cache_metadata(symbol, data)
            return data
        except Exception as e:
            logger.warning(
                "Failed to fetch fresh metadata from yfinance for %s: %s. Trying DB fallback.",
                symbol, e,
            )

        try:
            row = self._read_db_row(symbol)
            if row:
                self._warm_cache_from_row(symbol, row)
                return self._metadata_from_row(row)
        except Exception as db_err:
            logger.exception("Error loading fallback metadata from DB for %s: %s", symbol, db_err)

        raise MarketDataNotFoundError(f"Could not resolve price or metadata for symbol: {symbol}")

    # ------------------------------------------------------------------
    # Generic metadata accessors
    # ------------------------------------------------------------------

    def get_metadata_field(self, symbol: str, field: str) -> Any:
        """
        Generic getter for any resolved metadata field.
        Uses locking to prevent duplicate fetches on cache misses.
        """
        symbol = self._normalize_symbol(symbol)
        field_cache_map = {
            "price": "price",
            "sector": "sector",
            "market_cap": "cap",
            "company_name": "name",
        }
        if field not in field_cache_map:
            raise ValueError(f"Unsupported metadata field: {field}")

        cache_key = field_cache_map[field]
        allow_none = field == "market_cap"

        cached = self._get_cached_field(symbol, cache_key)
        if cached is not None:
            if cached == "None" and allow_none:
                return None
            return self._cast_value(field, cached)

        lock = self._fetch_lock if field == "price" else self._metadata_lock
        with lock:
            cached = self._get_cached_field(symbol, cache_key)
            if cached is not None:
                if cached == "None" and allow_none:
                    return None
                return self._cast_value(field, cached)

            data = self._resolve_and_update(symbol)
            raw = data.get(field)
            if raw is not None:
                return self._cast_value(field, raw)

            if allow_none:
                return None

        raise MarketDataNotFoundError(f"Resolved metadata for {symbol} but {field} was missing.")

    @staticmethod
    def _cast_value(field: str, value) -> Any:
        """Cast a cached/value string to the appropriate type."""
        if field == "price":
            return float(value)
        if field == "market_cap":
            return float(value) if value not in (None, "None") else None
        return str(value)

    # ------------------------------------------------------------------
    # Public getters
    # ------------------------------------------------------------------

    def get_price(self, symbol: str) -> float:
        return self.get_metadata_field(symbol, "price")

    def get_sector(self, symbol: str, db: Session = None) -> str:
        return self.get_metadata_field(symbol, "sector")

    def get_market_cap(self, symbol: str, db: Session = None) -> float | None:
        return self.get_metadata_field(symbol, "market_cap")

    def get_company_name(self, symbol: str, db: Session = None) -> str:
        return self.get_metadata_field(symbol, "company_name")

    def get_sectors_bulk(self, symbols: list[str]) -> dict[str, str]:
        return {s: self.get_sector(s) for s in symbols}

    # ------------------------------------------------------------------
    # Bulk price helpers
    # ------------------------------------------------------------------

    def get_prices_bulk(self, symbols: list[str]) -> dict[str, float]:
        normalized = [self._normalize_symbol(s) for s in symbols]
        logger.info("[MarketData] get_prices_bulk for %d symbols: %s", len(normalized), normalized)

        result: dict[str, float] = {}
        missing: list[str] = []
        for s in normalized:
            cached = self._get_cached_field(s, "price")
            if cached is not None:
                result[s] = float(cached)
            else:
                missing.append(s)

        if not missing:
            return result

        with self._bulk_price_lock:
            still_missing: list[str] = []
            for s in missing:
                cached = self._get_cached_field(s, "price")
                if cached is not None:
                    result[s] = float(cached)
                else:
                    still_missing.append(s)

            if not still_missing:
                return result

            logger.info("[yfinance] Bulk download for %d symbols: %s", len(still_missing), still_missing)
            yf_prices: dict[str, float] = {}
            unresolved: list[str] = []

            try:
                data = self._download_yfinance(
                    tickers=" ".join(still_missing),
                    period="1d",
                    group_by="ticker",
                )
                multi_symbol = len(still_missing) > 1
                for s in still_missing:
                    price_val = self._extract_latest_close(data, s, multi_symbol=multi_symbol)
                    if price_val is not None:
                        yf_prices[s] = price_val
                    else:
                        unresolved.append(s)
            except Exception as e:
                logger.error("Bulk yfinance price download failed after retries: %s", e)
                unresolved = still_missing.copy()

            if yf_prices:
                logger.info("[MarketData] Bulk saving %d fresh prices to DB and cache.", len(yf_prices))
                try:
                    self._save_market_prices_bulk_to_db({s: {"price": p} for s, p in yf_prices.items()})
                except Exception as db_err:
                    logger.exception("Error saving bulk yfinance prices to DB: %s", db_err)
                for s, p in yf_prices.items():
                    self._set_cached_field(s, "price", p, self.PRICE_TTL)
                    result[s] = p

            if unresolved:
                logger.info("[MarketData] Falling back to DB for %d unresolved symbols: %s", len(unresolved), unresolved)
                db_prices: dict[str, float] = {}
                try:
                    with self._get_db() as db:
                        rows = db.query(MarketPrice).filter(MarketPrice.symbol.in_(unresolved)).all()
                        for row in rows:
                            db_prices[row.symbol] = row.price
                except Exception as e:
                    logger.exception("Error reading fallback prices from DB: %s", e)

                for s in unresolved:
                    if s in db_prices:
                        result[s] = db_prices[s]
                        self._set_cached_field(s, "price", db_prices[s], self.PRICE_TTL)
                    else:
                        raise MarketDataNotFoundError(f"Could not resolve price for symbol: {s}")

        return result

    # ------------------------------------------------------------------
    # Bulk metadata
    # ------------------------------------------------------------------

    def get_metadata_bulk(self, symbols: list[str], db: Session = None) -> dict[str, dict[str, Any]]:
        """
        Fetch all metadata for a list of symbols in bulk.
        Returns: {symbol: metadata_dict}
        """
        normalized = [self._normalize_symbol(s) for s in symbols]
        logger.info("[MarketData] get_metadata_bulk for %d symbols: %s", len(normalized), normalized)
        result: dict[str, dict[str, Any]] = {}

        missing: list[str] = []
        for s in normalized:
            if self._all_metadata_cached(s):
                result[s] = self._cached_metadata(s)
            else:
                missing.append(s)

        if not missing:
            return result

        with self._metadata_lock:
            still_missing: list[str] = []
            for s in missing:
                if self._all_metadata_cached(s):
                    result[s] = self._cached_metadata(s)
                else:
                    still_missing.append(s)

            if not still_missing:
                return result

            logger.info("[yfinance] Parallel metadata fetch for %d symbols: %s", len(still_missing), still_missing)
            yf_updates: dict[str, dict[str, Any]] = {}
            unresolved: list[str] = []

            max_workers = min(len(still_missing), 16)
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_symbol = {executor.submit(self._fetch_yfinance_metadata, s): s for s in still_missing}
                for future in concurrent.futures.as_completed(future_to_symbol):
                    s = future_to_symbol[future]
                    try:
                        yf_updates[s] = future.result()
                    except Exception as e:
                        logger.warning("yfinance fetch failed during parallel bulk retrieval for %s: %s", s, e)
                        unresolved.append(s)

            if yf_updates:
                logger.info("[MarketData] Bulk saving %d fresh metadata sets to DB and cache.", len(yf_updates))
                try:
                    self._save_market_prices_bulk_to_db(yf_updates, db=db)
                except Exception as e:
                    logger.exception("Failed bulk database save: %s", e)

                for s, data in yf_updates.items():
                    self._cache_metadata(s, data)
                    result[s] = data

            if unresolved:
                logger.info("[MarketData] DB fallback for %d unresolved metadata symbols: %s", len(unresolved), unresolved)
                db_map: dict[str, dict[str, Any]] = {}
                try:
                    if db is not None:
                        rows = db.query(MarketPrice).filter(MarketPrice.symbol.in_(unresolved)).all()
                    else:
                        with self._get_db() as local_db:
                            rows = local_db.query(MarketPrice).filter(MarketPrice.symbol.in_(unresolved)).all()

                    for row in rows:
                        db_map[row.symbol] = self._metadata_from_row(row)
                except Exception as db_err:
                    logger.exception("Error bulk reading fallback metadata from DB: %s", db_err)

                still_unresolved: list[str] = []
                for s in unresolved:
                    row_dict = db_map.get(s)
                    if row_dict:
                        result[s] = row_dict
                        self._cache_metadata(s, row_dict)
                    else:
                        still_unresolved.append(s)

                if still_unresolved:
                    raise MarketDataNotFoundError(f"Could not resolve metadata for symbols: {still_unresolved}")

        return result

    # ------------------------------------------------------------------
    # Market snapshot bulk
    # ------------------------------------------------------------------

    def fetch_market_snapshot_bulk(self, symbols: list[str]) -> list[dict[str, Any]]:
        """
        Fetch a simple market snapshot (ticker, name, sector, price) for each symbol.
        """
        snapshots: list[dict[str, Any]] = []

        try:
            metadata_map = self.get_metadata_bulk(symbols)
        except Exception as e:
            logger.warning("Bulk metadata warm-up failed during snapshot retrieval: %s", e)
            metadata_map = {}

        for symbol in symbols:
            sym = self._normalize_symbol(symbol)
            try:
                data = metadata_map.get(sym)
                if data is None:
                    data = self._resolve_and_update(sym)

                snapshots.append({
                    "ticker": sym,
                    "company_name": data.get("company_name"),
                    "sector": data.get("sector"),
                    "current_price": data.get("price"),
                })
                logger.info("[MarketData] Snapshot resolved for %s.", sym)
            except Exception as e:
                logger.exception("Error resolving snapshot for %s: %s", sym, e)

        return snapshots

    def fetch_market_snapshot_bulk_df(self, symbols: list[str]) -> pd.DataFrame:
        """Same as fetch_market_snapshot_bulk but returns a pandas DataFrame."""
        return pd.DataFrame(self.fetch_market_snapshot_bulk(symbols))

    # ------------------------------------------------------------------
    # Specialized Copilot Ticker/Dividend Tools
    # ------------------------------------------------------------------

    def fetch_ticker_data(self, symbol: str) -> dict[str, Any]:
        """Fetch detailed informational stats for a symbol."""
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
        fast_info = self._get_fast_info(ticker)

        return {
            "symbol": symbol.upper(),
            "fetched_at": self._utcnow().isoformat(),
            "price": (
                fast_info.get("lastPrice")
                or info.get("regularMarketPrice")
                or info.get("currentPrice")
            ),
            "market_cap": info.get("marketCap") or fast_info.get("marketCap"),
            "company_name": (
                info.get("longName")
                or info.get("shortName")
                or symbol.upper()
            ),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "beta": info.get("beta"),
            "trailing_pe": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "eps_trailing_twelve_months": info.get("trailingEps"),
            "eps_forward": info.get("forwardEps"),
            "52w_low": info.get("fiftyTwoWeekLow") or fast_info.get("yearLow"),
            "52w_high": info.get("fiftyTwoWeekHigh") or fast_info.get("yearHigh"),
            "day_low": info.get("dayLow") or fast_info.get("dayLow"),
            "day_high": info.get("dayHigh") or fast_info.get("dayHigh"),
            "open": info.get("open") or fast_info.get("open"),
            "previous_close": info.get("previousClose") or fast_info.get("previousClose"),
            "volume": info.get("volume") or fast_info.get("lastVolume"),
        }

    def get_dividend(self, symbol: str) -> list[dict[str, Any]]:
        """Fetch the last 5 years dividend history for a given stock symbol."""
        ticker = yf.Ticker(symbol)
        dividends = ticker.dividends

        if dividends is None or dividends.empty:
            return []
        
        # Localize or drop tz
        if dividends.index.tz is not None:
            dividends.index = dividends.index.tz_localize(None)

        cutoff_date = pd.Timestamp.now() - pd.DateOffset(years=5)
        five_years = dividends[dividends.index >= cutoff_date]

        records = []
        for ts, val in five_years.items():
            records.append({
                "date": ts.strftime("%Y-%m-%d"),
                "dividend": float(val)
            })
        return records

    def fetch_ticker_data_bulk(self, symbols: list[str]) -> dict[str, Any]:
        """Fetch detailed stats in parallel using ThreadPoolExecutor."""
        result = {}
        max_workers = min(len(symbols), 16)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_symbol = {executor.submit(self.fetch_ticker_data, s): s for s in symbols}
            for future in concurrent.futures.as_completed(future_to_symbol):
                s = future_to_symbol[future]
                try:
                    result[s] = future.result()
                except Exception as e:
                    logger.error("Error fetching ticker data for %s: %s", s, e)
                    result[s] = {"symbol": s.upper(), "error": str(e)}
        return result

    def get_dividend_bulk(self, symbols: list[str]) -> dict[str, Any]:
        """Fetch dividend history in parallel using ThreadPoolExecutor."""
        result = {}
        max_workers = min(len(symbols), 16)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_symbol = {executor.submit(self.get_dividend, s): s for s in symbols}
            for future in concurrent.futures.as_completed(future_to_symbol):
                s = future_to_symbol[future]
                try:
                    result[s] = future.result()
                except Exception as e:
                    logger.error("Error fetching dividend for %s: %s", s, e)
                    result[s] = []
        return result

    # ------------------------------------------------------------------
    # Historical data
    # ------------------------------------------------------------------

    def get_historical_prices_bulk(
        self, symbols: list[str], start_date: datetime, end_date: datetime
    ) -> dict[str, dict[str, float]]:
        """
        Download historical daily closing prices for multiple symbols in bulk.
        Returns: {symbol: {date_str: price_float}}
        """
        symbols = [self._normalize_symbol(s) for s in symbols]
        result = {s: {} for s in symbols}

        if not symbols:
            return result

        start_str = start_date.strftime("%Y-%m-%d")
        end_str = (end_date + timedelta(days=1)).strftime("%Y-%m-%d")

        logger.info(
            "[yfinance] Downloading historical closes for %d symbols from %s to %s: %s",
            len(symbols), start_str, end_str, symbols,
        )

        try:
            data = self._download_yfinance(
                tickers=" ".join(symbols),
                start=start_str,
                end=end_str,
                interval="1d",
                group_by="ticker",
            )
        except Exception as e:
            logger.error("Historical yfinance download failed after retries: %s", e)
            return result

        if data is None or data.empty:
            return result

        for s in symbols:
            try:
                if isinstance(data.columns, pd.MultiIndex):
                    td = data[s]
                else:
                    td = data

                if td is not None and not td.empty:
                    close_col = "Close" if "Close" in td.columns else ("Adj Close" if "Adj Close" in td.columns else None)
                    if close_col is None:
                        continue
                    for ts, val in td[close_col].dropna().items():
                        result[s][ts.strftime("%Y-%m-%d")] = float(val)
            except Exception as e:
                logger.exception("Error extracting history for %s: %s", s, e)

        return result

    def get_prices_on_date_bulk(self, symbols: list[str], target_date: date | datetime) -> dict[str, float]:
        """
        Get closing prices for symbols on a specific date.
        Falls back to the last available close before that date (handles weekends/holidays).
        """
        if isinstance(target_date, datetime):
            target_day = target_date.date()
        else:
            target_day = target_date

        start_date = datetime.combine(target_day - timedelta(days=5), datetime.min.time())
        end_date = datetime.combine(target_day, datetime.max.time())
        history = self.get_historical_prices_bulk(symbols, start_date, end_date)

        result: dict[str, float] = {}
        for s in symbols:
            s_norm = self._normalize_symbol(s)
            sym_hist = history.get(s_norm, {})
            if sym_hist:
                last_date = sorted(sym_hist.keys())[-1]
                result[s_norm] = sym_hist[last_date]
        return result

    def get_historical_performance_bulk(
        self, symbols: list[str], start_date: datetime, end_date: datetime
    ) -> dict[str, dict[str, Any]]:
        """
        Get historical performance (daily closing prices) for multiple symbols in bulk.
        Returns: {"historical_performance": {symbol: {...}}}
        """
        raw_history = self.get_historical_prices_bulk(symbols, start_date, end_date)

        perf_data: dict[str, dict[str, Any]] = {}
        for symbol in symbols:
            symbol_norm = self._normalize_symbol(symbol)
            symbol_prices = raw_history.get(symbol_norm, {})
            if not symbol_prices:
                continue

            sorted_dates = sorted(symbol_prices.keys())
            if len(sorted_dates) < 2:
                continue

            start_date_str = sorted_dates[0]
            end_date_str = sorted_dates[-1]
            start_price = symbol_prices[start_date_str]
            end_price = symbol_prices[end_date_str]

            if start_price == 0:
                continue

            return_percent = ((end_price - start_price) / start_price) * 100
            step = max(1, len(sorted_dates) // 10)
            sample_dates = sorted_dates[::step]
            if sorted_dates[-1] not in sample_dates:
                sample_dates.append(sorted_dates[-1])

            price_sample = {d: round(symbol_prices[d], 2) for d in sample_dates}

            perf_data[symbol] = {
                "start_date": start_date_str,
                "start_price": round(start_price, 2),
                "end_date": end_date_str,
                "end_price": round(end_price, 2),
                "return_percent": round(return_percent, 2),
                "price_history_sample": price_sample,
            }

        return {"historical_performance": perf_data}

    # ------------------------------------------------------------------
    # DB price update job
    # ------------------------------------------------------------------

    def update_all_prices_in_db(self) -> None:
        from app.models.transaction import Transaction
        from app.models.watchlist_item import WatchlistItem

        try:
            with self._get_db() as db:
                all_symbols = list({
                    self._normalize_symbol(s)
                    for s in (
                        [r[0] for r in db.query(Transaction.symbol).distinct().all()]
                        + [r[0] for r in db.query(WatchlistItem.symbol).distinct().all()]
                        + [r[0] for r in db.query(MarketPrice.symbol).distinct().all()]
                    )
                    if s
                })

            if not all_symbols:
                logger.info("No symbols found to update.")
                return

            logger.info("Updating LTP for %d active symbols in DB...", len(all_symbols))
            prices: dict[str, float] = {}

            if len(all_symbols) == 1:
                s = all_symbols[0]
                try:
                    data = self._fetch_yfinance_metadata(s)
                    prices[s] = data["price"]
                except Exception:
                    logger.exception("Error fetching single-symbol fast price during DB update for %s", s)
            else:
                try:
                    data = self._download_yfinance(
                        tickers=" ".join(all_symbols),
                        period="1d",
                        group_by="ticker",
                    )
                    multi_symbol = len(all_symbols) > 1
                    for s in all_symbols:
                        price_val = self._extract_latest_close(data, s, multi_symbol=multi_symbol)
                        if price_val is not None:
                            prices[s] = price_val
                except Exception as e:
                    logger.exception("Bulk download failed while updating DB prices: %s", e)

            if prices:
                self._save_market_prices_bulk_to_db({s: {"price": price} for s, price in prices.items()})
                for s, price in prices.items():
                    self._set_cached_field(s, "price", price, self.PRICE_TTL)
                logger.info("Successfully updated LTP for %d symbols.", len(prices))
        except Exception as e:
            logger.exception("Error running update_all_prices_in_db: %s", e)


market_data_service = MarketDataService()



