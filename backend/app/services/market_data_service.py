import logging
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import yfinance as yf

from app.db.session import SessionLocal
from app.models.market_price import MarketPrice
from app.core.cache import cache_manager

logger = logging.getLogger(__name__)


class MarketDataService:
    FALLBACK_PRICE = 100.0
    FALLBACK_SECTOR = "Other"
    FALLBACK_MARKET_CAP = 1_000_000_000.0
    # Name fallback is always symbol

    def __init__(self):
        # Relying on centralized Redis cache_manager instead of internal memory caches
        pass

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

    def _save_price_to_db(self, symbol: str, price: float) -> None:
        symbol = self._normalize_symbol(symbol)
        now_utc = self._utcnow()
        try:
            with self._get_db() as db:
                market_price = (
                    db.query(MarketPrice)
                    .filter(MarketPrice.symbol == symbol)
                    .first()
                )
                if market_price:
                    market_price.price = price
                    market_price.updated_at = now_utc
                else:
                    db.add(
                        MarketPrice(
                            symbol=symbol,
                            price=price,
                            updated_at=now_utc,
                        )
                    )
        except Exception as e:
            logger.exception("Error saving price to DB for %s: %s", symbol, e)

    def _get_fast_info(self, ticker: yf.Ticker) -> dict:
        """Wrapper to access fast_info safely across yfinance versions."""
        try:
            # Some versions recommend get_fast_info(); fall back to property.[web:25][web:18]
            if hasattr(ticker, "get_fast_info"):
                return ticker.get_fast_info() or {}
            return dict(ticker.fast_info or {})
        except Exception:
            return {}

    def _fetch_ticker_data(self, symbol: str) -> None:
        """Fetches unified ticker data safely and updates caches."""
        symbol = self._normalize_symbol(symbol)
        now = self._utcnow()

        # Default fallbacks
        price = self.FALLBACK_PRICE
        sector = self.FALLBACK_SECTOR
        market_cap = self.FALLBACK_MARKET_CAP
        name = symbol

        try:
            ticker = yf.Ticker(symbol)
            fast_info = self._get_fast_info(ticker)
            info = ticker.info or {}

            # 1. Price resolution logic
            price_val = fast_info.get("lastPrice") or fast_info.get("last_price")
            if price_val is None:
                price_val = (
                    info.get("regularMarketPrice")
                    or info.get("currentPrice")
                )

            if price_val is None:
                history = ticker.history(period="1d")
                if not history.empty:
                    price_val = history["Close"].dropna().iloc[-1]

            if price_val and price_val > 0:
                price = float(price_val)

            # 2. Metadata components
            sector = info.get("sector") or self.FALLBACK_SECTOR

            cap_val = info.get("marketCap")
            if cap_val is None:
                cap_val = fast_info.get("marketCap") or fast_info.get("market_cap")
            if cap_val and cap_val > 0:
                market_cap = float(cap_val)

            name = info.get("longName") or info.get("shortName") or symbol

            # Save to DB immediately if price is valid
            self._save_price_to_db(symbol, price)

        except Exception as e:
            logger.exception("Error fetching yfinance metadata for %s: %s", symbol, e)

        finally:
            # Always ensure cache fills
            cache_manager.set(f"market_data:price:{symbol}", price, ttl=300)
            cache_manager.set(f"market_data:sector:{symbol}", sector, ttl=31536000)
            cache_manager.set(f"market_data:cap:{symbol}", market_cap, ttl=2592000)
            cache_manager.set(f"market_data:name:{symbol}", name, ttl=31536000)

    def get_price(self, symbol: str) -> float:
        symbol = self._normalize_symbol(symbol)

        cached = cache_manager.get(f"market_data:price:{symbol}")
        if cached is not None:
            return float(cached)

        try:
            with self._get_db() as db:
                market_price = (
                    db.query(MarketPrice)
                    .filter(MarketPrice.symbol == symbol)
                    .first()
                )
                if market_price:
                    db_price = market_price.price
                    cache_manager.set(f"market_data:price:{symbol}", db_price, ttl=300)
                    return db_price
        except Exception as e:
            logger.exception("Error reading LTP from DB for %s: %s", symbol, e)

        # Fallback to single fetch
        self._fetch_ticker_data(symbol)
        fetched = cache_manager.get(f"market_data:price:{symbol}")
        return float(fetched) if fetched is not None else self.FALLBACK_PRICE

    def get_sector(self, symbol: str) -> str:
        symbol = self._normalize_symbol(symbol)
        cached = cache_manager.get(f"market_data:sector:{symbol}")
        if cached is not None:
            return str(cached)
        self._fetch_ticker_data(symbol)
        fetched = cache_manager.get(f"market_data:sector:{symbol}")
        return str(fetched) if fetched is not None else self.FALLBACK_SECTOR

    def get_sectors_bulk(self, symbols: list[str]) -> dict[str, str]:
        result = {}
        for s in symbols:
            result[s] = self.get_sector(s)
        return result

    def get_market_cap(self, symbol: str) -> float:
        symbol = self._normalize_symbol(symbol)
        cached = cache_manager.get(f"market_data:cap:{symbol}")
        if cached is not None:
            return float(cached)
        self._fetch_ticker_data(symbol)
        fetched = cache_manager.get(f"market_data:cap:{symbol}")
        return float(fetched) if fetched is not None else self.FALLBACK_MARKET_CAP

    def get_company_name(self, symbol: str) -> str:
        symbol = self._normalize_symbol(symbol)
        cached = cache_manager.get(f"market_data:name:{symbol}")
        if cached is not None:
            return str(cached)
        self._fetch_ticker_data(symbol)
        fetched = cache_manager.get(f"market_data:name:{symbol}")
        return str(fetched) if fetched is not None else symbol

    def get_prices_bulk(self, symbols: list[str]) -> dict[str, float]:
        missing: list[str] = []
        result: dict[str, float] = {}

        normalized_symbols = [self._normalize_symbol(s) for s in symbols]

        for s in normalized_symbols:
            cached = cache_manager.get(f"market_data:price:{s}")
            if cached is not None:
                result[s] = float(cached)
            else:
                missing.append(s)

        if missing:
            db_prices: dict[str, float] = {}
            try:
                with self._get_db() as db:
                    db_rows = (
                        db.query(MarketPrice)
                        .filter(MarketPrice.symbol.in_(missing))
                        .all()
                    )
                    for row in db_rows:
                        db_prices[row.symbol] = row.price
            except Exception as e:
                logger.exception("Error bulk reading LTP from DB: %s", e)

            still_missing: list[str] = []
            for s in missing:
                if s in db_prices:
                    result[s] = db_prices[s]
                    cache_manager.set(f"market_data:price:{s}", db_prices[s], ttl=300)
                else:
                    still_missing.append(s)

            if still_missing:
                try:
                    if len(still_missing) == 1:
                        s = still_missing[0]
                        result[s] = self.get_price(s)
                    else:
                        tickers_str = " ".join(still_missing)
                        data = yf.download(
                            tickers=tickers_str,
                            period="1d",
                            group_by="ticker",
                            progress=False,
                        )
                        db_updates: dict[str, float] = {}

                        for s in still_missing:
                            s_norm = self._normalize_symbol(s)
                            price_val = None
                            try:
                                ticker_data = (
                                    data[s_norm]
                                    if len(still_missing) > 1
                                    else data
                                )
                                if (
                                    ticker_data is not None
                                    and not ticker_data.empty
                                    and "Close" in ticker_data
                                ):
                                    price_val = (
                                        ticker_data["Close"]
                                        .dropna()
                                        .iloc[-1]
                                    )
                            except Exception:
                                pass

                            if not price_val or price_val <= 0:
                                price = self.FALLBACK_PRICE
                            else:
                                price = float(price_val)

                            cache_manager.set(f"market_data:price:{s_norm}", price, ttl=300)

                            db_updates[s_norm] = price
                            result[s_norm] = price

                        if db_updates:
                            try:
                                now_utc = self._utcnow()
                                with self._get_db() as db:
                                    for s_sym, p in db_updates.items():
                                        market_price = (
                                            db.query(MarketPrice)
                                            .filter(MarketPrice.symbol == s_sym)
                                            .first()
                                        )
                                        if market_price:
                                            market_price.price = p
                                            market_price.updated_at = now_utc
                                        else:
                                            db.add(
                                                MarketPrice(
                                                    symbol=s_sym,
                                                    price=p,
                                                    updated_at=now_utc,
                                                )
                                            )
                            except Exception as e:
                                logger.exception(
                                    "Error bulk saving prices to DB: %s", e
                                )
                except Exception as e:
                    logger.exception(
                        "Bulk download error: %s. Falling back to default prices.",
                        e,
                    )
                    for s in still_missing:
                        s_norm = self._normalize_symbol(s)
                        result[s_norm] = self.FALLBACK_PRICE
                        cache_manager.set(f"market_data:price:{s_norm}", self.FALLBACK_PRICE, ttl=300)

        return result

    def get_historical_prices_bulk(
        self, symbols: list, start_date: datetime, end_date: datetime
    ) -> dict:
        """
        Download historical daily closing prices for multiple symbols in bulk.
        Returns a dict: {symbol: {date_str: price_float}}
        """
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = (end_date + timedelta(days=1)).strftime("%Y-%m-%d")
        
        symbols = [s.upper().strip() for s in symbols]
        result = {s: {} for s in symbols}
        
        if not symbols:
            return result
            
        try:
            tickers_str = " ".join(symbols)
            data = yf.download(
                tickers=tickers_str,
                start=start_str,
                end=end_str,
                interval="1d",
                group_by="ticker",
                progress=False,
            )
            
            for s in symbols:
                try:
                    ticker_data = data[s] if len(symbols) > 1 else data
                    if ticker_data is not None and not ticker_data.empty:
                        close_series = ticker_data["Close"].dropna()
                        for date, val in close_series.items():
                            date_str = date.strftime("%Y-%m-%d")
                            result[s][date_str] = float(val)
                except Exception as e:
                    logger.exception("Error extracting history for %s: %s", s, e)
        except Exception as e:
            logger.exception("Historical bulk download failed: %s", e)
            
        return result

    def get_prices_on_date_bulk(
        self, symbols: list[str], target_date
    ) -> dict[str, float]:
        """
        Get the closing prices for a list of symbols on a specific date.
        If the date is a weekend/holiday, falls back to the last available closing price before that date.
        """
        from datetime import date as _date
        # Fetch history for 5 days preceding target_date to handle holidays/weekends
        start_date = datetime.combine(target_date - timedelta(days=5), datetime.min.time())
        end_date = datetime.combine(target_date, datetime.max.time())
        
        history = self.get_historical_prices_bulk(symbols, start_date, end_date)
        
        result = {}
        for s in symbols:
            s_norm = self._normalize_symbol(s)
            symbol_history = history.get(s_norm, {})
            if symbol_history:
                # Sort dates ascending and pick the last one (which is closest to target_date)
                sorted_dates = sorted(symbol_history.keys())
                last_date = sorted_dates[-1]
                result[s_norm] = symbol_history[last_date]
                
        return result

    def update_all_prices_in_db(self) -> None:
        from app.models.transaction import Transaction
        from app.models.watchlist_item import WatchlistItem

        try:
            with self._get_db() as db:
                holding_symbols = [
                    r[0] for r in db.query(Transaction.symbol).distinct().all()
                ]
                watchlist_symbols = [
                    r[0] for r in db.query(WatchlistItem.symbol).distinct().all()
                ]
                db_symbols = [
                    r[0] for r in db.query(MarketPrice.symbol).distinct().all()
                ]

            all_symbols = list(
                {
                    self._normalize_symbol(s)
                    for s in (holding_symbols + watchlist_symbols + db_symbols)
                    if s
                }
            )
            if not all_symbols:
                logger.info("No symbols found to update.")
                return

            logger.info(
                "Updating LTP for %d active symbols in DB...", len(all_symbols)
            )
            prices: dict[str, float] = {}

            if len(all_symbols) == 1:
                s = all_symbols[0]
                ticker = yf.Ticker(s)
                try:
                    fast_info = self._get_fast_info(ticker)
                    p = fast_info.get("lastPrice") or fast_info.get("last_price")
                    if not p:
                        info = ticker.info or {}
                        p = info.get("regularMarketPrice") or info.get(
                            "currentPrice"
                        )
                    if p:
                        prices[s] = float(p)
                except Exception:
                    logger.exception(
                        "Error fetching single-symbol fast price for %s", s
                    )
            else:
                tickers_str = " ".join(all_symbols)
                data = yf.download(
                    tickers=tickers_str,
                    period="1d",
                    group_by="ticker",
                    progress=False,
                )
                for s in all_symbols:
                    try:
                        ticker_data = data[s] if len(all_symbols) > 1 else data
                        if (
                            ticker_data is not None
                            and not ticker_data.empty
                            and "Close" in ticker_data
                        ):
                            prices[s] = float(
                                ticker_data["Close"].dropna().iloc[-1]
                            )
                    except Exception:
                        # Skip symbol but keep others
                        logger.exception(
                            "Error extracting close price for %s", s
                        )

            if prices:
                now_utc = self._utcnow()
                with self._get_db() as db:
                    for s, price in prices.items():
                        market_price = (
                            db.query(MarketPrice)
                            .filter(MarketPrice.symbol == s)
                            .first()
                        )
                        if market_price:
                            market_price.price = price
                            market_price.updated_at = now_utc
                        else:
                            db.add(
                                MarketPrice(
                                    symbol=s,
                                    price=price,
                                    updated_at=now_utc,
                                )
                            )

                        cache_manager.set(f"market_data:price:{s}", price, ttl=300)

                logger.info(
                    "Successfully updated LTP for %d symbols in database.",
                    len(prices),
                )
        except Exception as e:
            logger.exception("Error running update_all_prices_in_db: %s", e)

market_data_service = MarketDataService()