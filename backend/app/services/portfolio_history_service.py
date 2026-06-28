import json
import logging
import re
import time
from datetime import date, datetime, timedelta
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from app.models.transaction import Transaction
from app.models.portfolio_daily_history import PortfolioDailyHistory
from app.services.market_data_service import market_data_service
from app.core.cache import cache_manager

logger = logging.getLogger(__name__)


class PortfolioHistoryService:
    def rebuild_history(self, db: Session, user_id: str, from_date=None, force=False) -> None:
        """
        Rebuild the daily valuation history for the user from from_date to today.
        If from_date is None, rebuild the entire history from the earliest transaction.
        """
        logger.info(f"[PortfolioHistoryService] rebuild_history: Rebuild requested for user {user_id}. from_date={from_date}, force={force}")
        try:
            # 1. Acquire lock on the user row to prevent concurrent history rebuild conflicts (skip on SQLite)
            from sqlalchemy import text
            if db.bind.dialect.name != "sqlite":
                logger.info(f"[PortfolioHistoryService] rebuild_history: Acquiring row lock for user {user_id}")
                db.execute(
                    text("SELECT id FROM users WHERE id = :user_id FOR UPDATE;"),
                    {"user_id": user_id}
                )
                logger.info(f"[PortfolioHistoryService] rebuild_history: Lock acquired successfully.")
            else:
                logger.info(f"[PortfolioHistoryService] rebuild_history: SQLite detected, skipping row lock.")
            
            # 2. Double-check if history was already rebuilt by a concurrent request
            if not force:
                today = datetime.utcnow().date()
                latest = db.query(PortfolioDailyHistory).filter(
                    PortfolioDailyHistory.user_id == user_id
                ).order_by(PortfolioDailyHistory.captured_at.desc()).first()
                if latest and latest.captured_at >= today:
                    logger.info(f"[PortfolioHistoryService] rebuild_history: History already rebuilt for today {today} (latest: {latest.captured_at}). Skipping.")
                    db.commit()
                    return

            # 3. Fetch all transactions for this user chronologically
            transactions = (
                db.query(Transaction)
                .filter(Transaction.user_id == user_id)
                .order_by(Transaction.executed_at.asc())
                .all()
            )
            
            if not transactions:
                # Delete all snapshots if no transactions exist
                logger.info(f"[PortfolioHistoryService] rebuild_history: No transactions found for user {user_id}. Deleting all historical snapshots.")
                db.query(PortfolioDailyHistory).filter(PortfolioDailyHistory.user_id == user_id).delete()
                db.commit()
                return
                
            earliest_tx_date = min(t.executed_at for t in transactions).date()
            logger.info(f"[PortfolioHistoryService] rebuild_history: Found {len(transactions)} transactions. Earliest transaction date: {earliest_tx_date}")
            
            # Normalize from_date
            if from_date is not None:
                if isinstance(from_date, str):
                    try:
                        from_date = datetime.strptime(from_date, "%Y-%m-%d").date()
                    except ValueError:
                        from_date = earliest_tx_date
                elif isinstance(from_date, datetime):
                    from_date = from_date.date()
                elif not isinstance(from_date, date):
                    from_date = earliest_tx_date
            else:
                from_date = earliest_tx_date

            # Clamp from_date to earliest transaction date
            if from_date < earliest_tx_date:
                from_date = earliest_tx_date
                
            logger.info(f"[PortfolioHistoryService] rebuild_history: Rebuild range start normalized to: {from_date}")
            
            # 4. Delete existing records from from_date onwards (committed at the end)
            logger.info(f"[PortfolioHistoryService] rebuild_history: Deleting existing records on or after {from_date}")
            deleted_count = db.query(PortfolioDailyHistory).filter(
                PortfolioDailyHistory.user_id == user_id,
                PortfolioDailyHistory.captured_at >= from_date
            ).delete()
            logger.info(f"[PortfolioHistoryService] rebuild_history: Deleted {deleted_count} stale records.")
            
            # 3. Simulate past transactions up to the day before from_date
            holdings = {}  # symbol -> {"qty": float, "cost": float}
            past_txs = [t for t in transactions if t.executed_at.date() < from_date]
            logger.info(f"[PortfolioHistoryService] rebuild_history: Simulating {len(past_txs)} past transactions to calculate cost basis on {from_date - timedelta(days=1)}")
            
            for tx in past_txs:
                symbol = tx.symbol.upper().strip()
                qty = float(tx.quantity)
                price = float(tx.price)
                fees = float(tx.fees or 0.0)
                
                if tx.transaction_type == "BUY":
                    h = holdings.get(symbol, {"qty": 0.0, "cost": 0.0})
                    new_qty = h["qty"] + qty
                    new_cost = h["cost"] + (qty * price) + fees
                    holdings[symbol] = {"qty": new_qty, "cost": new_cost}
                elif tx.transaction_type == "SELL":
                    h = holdings.get(symbol)
                    if h:
                        new_qty = max(0.0, h["qty"] - qty)
                        if h["qty"] > 0:
                            cost_per_share = h["cost"] / h["qty"]
                            new_cost = max(0.0, h["cost"] - (qty * cost_per_share))
                        else:
                            new_cost = 0.0
                            
                        if new_qty == 0:
                            holdings.pop(symbol, None)
                        else:
                            holdings[symbol] = {"qty": new_qty, "cost": new_cost}
                            
            logger.info(f"[PortfolioHistoryService] rebuild_history: Simulated holdings prior to {from_date}: {holdings}")
            
            # 4. Fetch bulk historical daily closing prices for the active range
            active_txs = [t for t in transactions if t.executed_at.date() >= from_date]
            active_symbols = list(set(list(holdings.keys()) + [t.symbol for t in active_txs]))
            
            # Fetch starting 7 days before from_date to pre-populate last_known_prices, clamped to earliest transaction date
            fetch_start_date = from_date - timedelta(days=7)
            if fetch_start_date < earliest_tx_date:
                fetch_start_date = earliest_tx_date
                
            start_datetime = datetime.combine(fetch_start_date, datetime.min.time())
            today = datetime.utcnow().date()
            end_datetime = datetime.combine(today, datetime.min.time())
            
            historical_prices = {}
            if active_symbols:
                logger.info(f"[PortfolioHistoryService] rebuild_history: Requesting bulk historical prices for active symbols {active_symbols} from {fetch_start_date} to {today}")
                historical_prices = market_data_service.get_historical_prices_bulk(
                    active_symbols, start_datetime, end_datetime
                )
                
            # 5. Simulate daily balances and insert new snapshots
            last_known_prices = {}
            # Pre-populate last known prices for holdings carried over from prior to from_date
            check_date = fetch_start_date
            while check_date < from_date:
                check_date_str = check_date.strftime("%Y-%m-%d")
                for symbol in active_symbols:
                    price = historical_prices.get(symbol, {}).get(check_date_str)
                    if price is not None:
                        last_known_prices[symbol] = price
                check_date += timedelta(days=1)
                
            current_date = datetime.combine(from_date, datetime.min.time())
            logger.info(f"[PortfolioHistoryService] rebuild_history: Starting simulation loop from {from_date} to {today} ({ (today - from_date).days + 1 } days)")
            
            snapshots_count = 0
            while current_date.date() <= today:
                date_val = current_date.date()
                date_str = date_val.strftime("%Y-%m-%d")
                
                # Apply transaction mutations of current_date
                txs_on_date = [t for t in active_txs if t.executed_at.date() == date_val]
                for tx in txs_on_date:
                    symbol = tx.symbol.upper().strip()
                    qty = float(tx.quantity)
                    price = float(tx.price)
                    fees = float(tx.fees or 0.0)
                    
                    if tx.transaction_type == "BUY":
                        h = holdings.get(symbol, {"qty": 0.0, "cost": 0.0})
                        new_qty = h["qty"] + qty
                        new_cost = h["cost"] + (qty * price) + fees
                        holdings[symbol] = {"qty": new_qty, "cost": new_cost}
                    elif tx.transaction_type == "SELL":
                        h = holdings.get(symbol)
                        if h:
                            new_qty = max(0.0, h["qty"] - qty)
                            if h["qty"] > 0:
                                cost_per_share = h["cost"] / h["qty"]
                                new_cost = max(0.0, h["cost"] - (qty * cost_per_share))
                            else:
                                new_cost = 0.0
                                
                            if new_qty == 0:
                                holdings.pop(symbol, None)
                            else:
                                holdings[symbol] = {"qty": new_qty, "cost": new_cost}
                                
                # Recompute total value and cost
                total_value = 0.0
                total_cost = 0.0
                
                for symbol, h in holdings.items():
                    price = historical_prices.get(symbol, {}).get(date_str)
                    if price is not None:
                        last_known_prices[symbol] = price
                    else:
                        price = last_known_prices.get(symbol)
                        
                    if price is None:
                        price = h["cost"] / h["qty"] if h["qty"] > 0 else 100.0
                        
                    val = h["qty"] * price
                    total_value += val
                    total_cost += h["cost"]
                        
                # Create/insert snapshot
                db_hist = PortfolioDailyHistory(
                    user_id=user_id,
                    captured_at=date_val,
                    total_value=round(total_value, 2),
                    total_cost=round(total_cost, 2)
                )
                db.add(db_hist)
                snapshots_count += 1
                
                current_date += timedelta(days=1)
                
            db.commit()
            logger.info(f"[PortfolioHistoryService] rebuild_history: Successfully created {snapshots_count} history snapshots and committed to DB.")
            
        except Exception as e:
            logger.error(f"Failed to rebuild history for user {user_id}: {e}", exc_info=True)
            db.rollback()
            raise

    def calculate_historical_performance(self, db: Session, user_id: str) -> List[Dict[str, Any]]:
        """
        Query cached daily snapshots from the database. 
        Calculates missing days on-the-fly and serves live values for today.
        """
        try:
            cache_key = f"user_cache:{user_id}:historical_performance"
            cached_res = cache_manager.get(cache_key)
            if cached_res is not None:
                logger.debug(f"[PortfolioHistoryService] Cache HIT for historical_performance, user {user_id}")
                return cached_res

            today = datetime.utcnow().date()
            
            # Query existing history from database
            records = (
                db.query(PortfolioDailyHistory)
                .filter(PortfolioDailyHistory.user_id == user_id)
                .order_by(PortfolioDailyHistory.captured_at.asc())
                .all()
            )
            
            # 1. If database has no snapshots: rebuild
            if not records:
                has_tx = db.query(Transaction).filter(Transaction.user_id == user_id).first()
                if has_tx:
                    logger.info(f"[PortfolioHistoryService] calculate_historical_performance: No snapshot records found in DB. Triggering cold-start rebuild_history for user {user_id}.")
                    self.rebuild_history(db, user_id)
                    # Re-query
                    records = (
                        db.query(PortfolioDailyHistory)
                        .filter(PortfolioDailyHistory.user_id == user_id)
                        .order_by(PortfolioDailyHistory.captured_at.asc())
                        .all()
                    )
                else:
                    return []
                    
            # 2. Check if the latest snapshot is before today
            last_date = records[-1].captured_at if records else date.min
            rebuild_triggered = False
            if last_date < today:
                if last_date == today - timedelta(days=1):
                    today_record = PortfolioDailyHistory(
                        user_id=user_id,
                        captured_at=today,
                        total_value=0.0,
                        total_cost=0.0
                    )
                    db.add(today_record)
                    db.flush()
                    records.append(today_record)
                else:
                    logger.info(f"[PortfolioHistoryService] calculate_historical_performance: Snapshots missing since {last_date} (today is {today}). Triggering rebuild_history starting from {last_date} for user {user_id}.")
                    self.rebuild_history(db, user_id, from_date=last_date)
                    rebuild_triggered = True
                    # Re-query
                    records = (
                        db.query(PortfolioDailyHistory)
                        .filter(PortfolioDailyHistory.user_id == user_id)
                        .order_by(PortfolioDailyHistory.captured_at.asc())
                        .all()
                    )
                
            # 3. If today is the current day, update today's snapshot dynamically using real-time prices
            total_value = 0.0
            total_cost = 0.0
            dynamic_updated = False
            if records and records[-1].captured_at == today:
                from app.services.holdings_service import holdings_service
                holdings_res = holdings_service.calculate_holdings(db, user_id)
                
                total_value = holdings_res.summary.total_value
                total_cost = holdings_res.summary.total_cost
                
                today_record = db.query(PortfolioDailyHistory).filter(
                    PortfolioDailyHistory.user_id == user_id,
                    PortfolioDailyHistory.captured_at == today
                ).first()
                
                if today_record:
                    today_record.total_value = round(total_value, 2)
                    today_record.total_cost = round(total_cost, 2)
                    # Update local return data structure
                    records[-1].total_value = round(total_value, 2)
                    records[-1].total_cost = round(total_cost, 2)
                    dynamic_updated = True

            # Construct the response dict list BEFORE calling commit,
            # which prevents SQLAlchemy from expiring and unloading the attributes (avoiding N+1 selects).
            res = [
                {
                    "captured_at": r.captured_at.strftime("%Y-%m-%d") if isinstance(r.captured_at, (datetime, date)) else str(r.captured_at),
                    "total_value": round(r.total_value, 2),
                    "total_cost": round(r.total_cost, 2)
                }
                for r in records
            ]
            
            db.commit()
            
            # Print a single consolidated info log for standard requests
            if rebuild_triggered:
                logger.info(f"[PortfolioHistoryService] calculate_historical_performance: Rebuilt & fetched history for user {user_id}. Returned {len(res)} records.")
            elif dynamic_updated:
                logger.info(f"[PortfolioHistoryService] calculate_historical_performance: Calculated performance for user {user_id}. Returned {len(res)} records (Today dynamic: value={total_value:.2f}, cost={total_cost:.2f}).")
            else:
                logger.info(f"[PortfolioHistoryService] calculate_historical_performance: Returned {len(res)} records for user {user_id}.")
                
            cache_manager.set(cache_key, res, ttl=600)
            return res
        except Exception as e:
            logger.error(f"Failed to calculate historical performance for user {user_id}: {e}", exc_info=True)
            db.rollback()
            raise

    def calculate_portfolio_value_on_date(self, db: Session, user_id: str, target_date: datetime.date) -> Dict[str, Any]:
        """
        Calculate the portfolio total value, total cost, and active positions on a user-specified date
        using all transactions executed on or before that date.
        """
        logger.info(f"[PortfolioHistoryService] calculate_portfolio_value_on_date: Requested for user {user_id} on date {target_date}")
        target_datetime = datetime.combine(target_date, datetime.max.time())
        
        # 1. Fetch transactions executed on or before target_datetime
        logger.info(f"[PortfolioHistoryService] calculate_portfolio_value_on_date: Fetching transactions executed on or before {target_datetime}")
        transactions = (
            db.query(Transaction)
            .filter(Transaction.user_id == user_id, Transaction.executed_at <= target_datetime)
            .order_by(Transaction.executed_at.asc())
            .all()
        )
        
        if not transactions:
            logger.info(f"[PortfolioHistoryService] calculate_portfolio_value_on_date: No transactions found on or before {target_date}. Returning empty portfolio.")
            return {
                "date": target_date.strftime("%Y-%m-%d"),
                "total_value": 0.0,
                "total_cost": 0.0,
                "active_positions": []
            }
            
        logger.info(f"[PortfolioHistoryService] calculate_portfolio_value_on_date: Found {len(transactions)} transactions. Simulating holdings up to {target_date}...")
        # 2. Chronological forward simulation up to target_datetime
        holdings = {}  # symbol -> {"qty": float, "cost": float}
        for tx in transactions:
            symbol = tx.symbol.upper().strip()
            qty = float(tx.quantity)
            price = float(tx.price)
            fees = float(tx.fees or 0.0)
            
            if tx.transaction_type == "BUY":
                h = holdings.get(symbol, {"qty": 0.0, "cost": 0.0})
                new_qty = h["qty"] + qty
                new_cost = h["cost"] + (qty * price) + fees
                holdings[symbol] = {"qty": new_qty, "cost": new_cost}
            elif tx.transaction_type == "SELL":
                h = holdings.get(symbol)
                if h:
                    new_qty = max(0.0, h["qty"] - qty)
                    if h["qty"] > 0:
                        cost_per_share = h["cost"] / h["qty"]
                        new_cost = max(0.0, h["cost"] - (qty * cost_per_share))
                    else:
                        new_cost = 0.0
                        
                    if new_qty == 0:
                        holdings.pop(symbol, None)
                    else:
                        holdings[symbol] = {"qty": new_qty, "cost": new_cost}
                        
        # 3. Fetch prices on target_date in bulk
        active_symbols = list(holdings.keys())
        logger.info(f"[PortfolioHistoryService] calculate_portfolio_value_on_date: Simulated holdings on {target_date}: {holdings}. Requesting prices for symbols: {active_symbols}")
        prices = market_data_service.get_prices_on_date_bulk(active_symbols, target_date)
        
        total_value = 0.0
        total_cost = 0.0
        active_positions = []
        
        for symbol, h in holdings.items():
            price = prices.get(symbol)
            if price is None:
                price = h["cost"] / h["qty"] if h["qty"] > 0 else 0.0
                
            val = h["qty"] * price
            total_value += val
            total_cost += h["cost"]
            
            active_positions.append({
                "symbol": symbol,
                "quantity": h["qty"],
                "price": round(price, 2),
                "market_value": round(val, 2),
                "cost": round(h["cost"], 2)
            })
            
        logger.info(f"[PortfolioHistoryService] calculate_portfolio_value_on_date: Calculation completed. total_value={total_value:.2f}, total_cost={total_cost:.2f}, active_positions={len(active_positions)}")
        return {
            "date": target_date.strftime("%Y-%m-%d"),
            "total_value": round(total_value, 2),
            "total_cost": round(total_cost, 2),
            "active_positions": active_positions
        }

    def get_returns_history(self, db: Session, user_id: str) -> Dict[str, Any]:
        """
        Get compressed chronological historical returns and values.
        """
        cache_key = f"user_cache:{user_id}:returns_history"
        cached_res = cache_manager.get(cache_key)
        if cached_res is not None:
            logger.debug(f"[PortfolioHistoryService] Cache HIT for returns_history, user {user_id}")
            return cached_res

        history = self.calculate_historical_performance(db, user_id)
        if not history:
            res = {
                "dates": [],
                "total_values": [],
                "total_costs": [],
                "daily_returns": [],
                "cumulative_return_percent": 0.0
            }
            cache_manager.set(cache_key, res, ttl=600)
            return res
            
        dates = [x["captured_at"] for x in history]
        values = [x["total_value"] for x in history]
        costs = [x["total_cost"] for x in history]
        
        # Calculate daily returns adjusted for capital inflows/outflows
        daily_returns = [0.0]
        for i in range(1, len(history)):
            v_prev = history[i-1]["total_value"]
            v_curr = history[i]["total_value"]
            c_prev = history[i-1]["total_cost"]
            c_curr = history[i]["total_cost"]
            
            if v_prev > 0:
                ret = (v_curr - (c_curr - c_prev) - v_prev) / v_prev
            else:
                ret = 0.0
            daily_returns.append(round(ret, 5))
            
        current_value = values[-1]
        current_cost = costs[-1]
        cumulative_return_percent = ((current_value - current_cost) / current_cost * 100.0) if current_cost > 0 else 0.0
        
        res = {
            "dates": dates,
            "total_values": values,
            "total_costs": costs,
            "daily_returns": daily_returns,
            "cumulative_return_percent": round(cumulative_return_percent, 2)
        }
        cache_manager.set(cache_key, res, ttl=600)
        return res

    def calculate_risk_metrics(self, db: Session, user_id: str) -> Dict[str, Any]:
        """
        Computes key risk-adjusted return ratios and loss bounds from the daily return series.
        """
        cache_key = f"user_cache:{user_id}:risk_metrics"
        cached_res = cache_manager.get(cache_key)
        if cached_res is not None:
            logger.debug(f"[PortfolioHistoryService] Cache HIT for risk_metrics, user {user_id}")
            return cached_res

        history_data = self.get_returns_history(db, user_id)
        daily_returns = history_data["daily_returns"]
        if len(daily_returns) < 2:
            res = {
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "annualized_volatility": 0.0,
                "downside_deviation": 0.0,
                "max_drawdown": 0.0,
                "var_95": 0.0,
                "var_99": 0.0,
                "cvar_95": 0.0,
                "cvar_99": 0.0
            }
            cache_manager.set(cache_key, res, ttl=600)
            return res
            
        active_returns = daily_returns[1:]
        
        import numpy as np
        
        mean_return = np.mean(active_returns)
        std_return = np.std(active_returns, ddof=1) if len(active_returns) > 1 else 0.0
        
        # Risk-free rate (6.5% annual -> daily)
        rf_annual = 0.065
        rf_daily = rf_annual / 252.0
        
        # Annualized Volatility
        ann_volatility = std_return * np.sqrt(252)
        
        # Downside deviation
        downside_returns = [r for r in active_returns if r < rf_daily]
        if downside_returns:
            downside_dev = np.sqrt(np.sum([(r - rf_daily)**2 for r in downside_returns]) / len(active_returns))
            ann_downside_dev = downside_dev * np.sqrt(252)
        else:
            downside_dev = 0.0
            ann_downside_dev = 0.0
            
        # Sharpe & Sortino
        sharpe = ((mean_return - rf_daily) / std_return * np.sqrt(252)) if std_return > 0 else 0.0
        sortino = ((mean_return - rf_daily) / downside_dev * np.sqrt(252)) if downside_dev > 0 else 0.0
        
        # Max Drawdown
        max_dd = 0.0
        peak_multiplier = 1.0
        for x in zip(history_data["total_values"], history_data["total_costs"]):
            val, cost = x
            if cost > 0:
                mult = val / cost
                if mult > peak_multiplier:
                    peak_multiplier = mult
                dd = ((peak_multiplier - mult) / peak_multiplier) * 100.0
                if dd > max_dd:
                    max_dd = dd
                    
        # Historical Value at Risk (VaR)
        sorted_returns = np.sort(active_returns)
        idx_95 = int(len(sorted_returns) * 0.05)
        idx_99 = int(len(sorted_returns) * 0.01)
        
        var_95 = -sorted_returns[idx_95] if len(sorted_returns) > 0 else 0.0
        var_99 = -sorted_returns[idx_99] if len(sorted_returns) > 0 else 0.0
        
        # Conditional Value at Risk (cVaR)
        cvar_95_val = -np.mean(sorted_returns[:max(1, idx_95)]) if len(sorted_returns) > 0 else 0.0
        cvar_99_val = -np.mean(sorted_returns[:max(1, idx_99)]) if len(sorted_returns) > 0 else 0.0
        
        res = {
            "sharpe_ratio": round(float(sharpe), 3),
            "sortino_ratio": round(float(sortino), 3),
            "annualized_volatility": round(float(ann_volatility) * 100.0, 2),
            "downside_deviation": round(float(ann_downside_dev) * 100.0, 2),
            "max_drawdown": round(float(max_dd), 2),
            "var_95": round(float(var_95) * 100.0, 3),
            "var_99": round(float(var_99) * 100.0, 3),
            "cvar_95": round(float(cvar_95_val) * 100.0, 3),
            "cvar_99": round(float(cvar_99_val) * 100.0, 3)
        }
        cache_manager.set(cache_key, res, ttl=600)
        return res

    def compare_to_benchmark(self, db: Session, user_id: str) -> Dict[str, Any]:
        """
        Compares daily portfolio returns with the Nifty 50 index (^NSEI) benchmark.
        """
        cache_key = f"user_cache:{user_id}:benchmark_comparison"
        cached_res = cache_manager.get(cache_key)
        if cached_res is not None:
            logger.debug(f"[PortfolioHistoryService] Cache HIT for benchmark_comparison, user {user_id}")
            return cached_res

        history_data = self.get_returns_history(db, user_id)
        dates = history_data["dates"]
        daily_returns = history_data["daily_returns"]
        if len(daily_returns) < 2:
            res = {
                "beta": 1.0,
                "alpha_annualized": 0.0,
                "correlation": 0.0,
                "tracking_error": 0.0,
                "information_ratio": 0.0
            }
            cache_manager.set(cache_key, res, ttl=600)
            return res
            
        import numpy as np
        
        start_date = datetime.strptime(dates[0], "%Y-%m-%d")
        end_date = datetime.strptime(dates[-1], "%Y-%m-%d")
        
        index_ticker = "^NSEI"
        try:
            index_hist = market_data_service.get_historical_prices_bulk([index_ticker], start_date, end_date)
            index_closes = index_hist.get(index_ticker, {})
        except Exception as e:
            logger.warning("Failed to fetch Nifty 50 history for benchmark comparison: %s", e)
            index_closes = {}
            
        # Align index prices
        aligned_index_prices = []
        last_val = None
        for d_str in dates:
            val = index_closes.get(d_str)
            if val is not None:
                last_val = val
            elif last_val is None:
                sorted_dates = sorted(index_closes.keys())
                if sorted_dates:
                    last_val = index_closes[sorted_dates[0]]
                else:
                    last_val = 1.0
            aligned_index_prices.append(last_val)
            
        # Compute benchmark daily returns
        benchmark_returns = [0.0]
        for i in range(1, len(aligned_index_prices)):
            p_prev = aligned_index_prices[i-1]
            p_curr = aligned_index_prices[i]
            ret = (p_curr - p_prev) / p_prev if p_prev > 0 else 0.0
            benchmark_returns.append(ret)
            
        active_returns = daily_returns[1:]
        active_benchmark_returns = benchmark_returns[1:]
        
        try:
            cov_matrix = np.cov(active_returns, active_benchmark_returns, ddof=1)
            cov_pm = cov_matrix[0, 1]
            var_m = cov_matrix[1, 1]
            
            beta = cov_pm / var_m if var_m > 0 else 1.0
            corr = np.corrcoef(active_returns, active_benchmark_returns)[0, 1]
            
            # Annualize
            rf_annual = 0.065
            ann_ret_p = np.mean(active_returns) * 252
            ann_ret_m = np.mean(active_benchmark_returns) * 252
            alpha = ann_ret_p - (rf_annual + beta * (ann_ret_m - rf_annual))
            
            active_diff = np.array(active_returns) - np.array(active_benchmark_returns)
            tracking_error = np.std(active_diff, ddof=1) * np.sqrt(252) if len(active_diff) > 1 else 0.0
            info_ratio = (ann_ret_p - ann_ret_m) / tracking_error if tracking_error > 0 else 0.0
            
            # Sanitize NaN/inf values
            if np.isnan(beta) or np.isinf(beta):
                beta = 1.0
            if np.isnan(alpha) or np.isinf(alpha):
                alpha = 0.0
            if np.isnan(corr) or np.isinf(corr):
                corr = 0.0
            if np.isnan(tracking_error) or np.isinf(tracking_error):
                tracking_error = 0.0
            if np.isnan(info_ratio) or np.isinf(info_ratio):
                info_ratio = 0.0
        except Exception as e:
            logger.exception("Error calculating benchmark stats: %s", e)
            beta, alpha, corr, tracking_error, info_ratio = 1.0, 0.0, 0.0, 0.0, 0.0
            
        res = {
            "beta": round(float(beta), 3),
            "alpha_annualized": round(float(alpha) * 100.0, 2),
            "correlation": round(float(corr), 3),
            "tracking_error": round(float(tracking_error) * 100.0, 2),
            "information_ratio": round(float(info_ratio), 3)
        }
        cache_manager.set(cache_key, res, ttl=600)
        return res

    def calculate_asset_covariance(self, db: Session, user_id: str) -> Dict[str, Any]:
        """
        Calculate annualized covariance and correlation matrices of holdings.
        """
        cache_key = f"user_cache:{user_id}:asset_covariance"
        cached_res = cache_manager.get(cache_key)
        if cached_res is not None:
            logger.debug(f"[PortfolioHistoryService] Cache HIT for asset_covariance, user {user_id}")
            return cached_res

        import numpy as np
        from app.services.holdings_service import holdings_service

        try:
            holdings_res = holdings_service.calculate_holdings(db, user_id)
            active_symbols = [h.symbol for h in holdings_res.holdings if h.quantity > 0]
        except Exception as e:
            logger.exception("Error getting holdings: %s", e)
            active_symbols = []

        if len(active_symbols) < 2:
            res = {
                "symbols": active_symbols,
                "covariance_matrix": [],
                "correlation_matrix": []
            }
            cache_manager.set(cache_key, res, ttl=600)
            return res

        # Fetch 1 year history
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=365)

        try:
            prices_hist = market_data_service.get_historical_prices_bulk(
                active_symbols,
                start_date,
                end_date
            )
        except Exception as e:
            logger.exception("Error fetching prices for covariance: %s", e)
            prices_hist = {}

        # Keep only symbols with price data
        valid_symbols = [
            s for s in active_symbols
            if s in prices_hist and len(prices_hist[s]) > 0
        ]

        if len(valid_symbols) < 2:
            res = {
                "symbols": valid_symbols,
                "covariance_matrix": [],
                "correlation_matrix": []
            }
            cache_manager.set(cache_key, res, ttl=600)
            return res

        # Use only common dates (avoids fake filling/lookahead)
        common_dates = sorted(
            set.intersection(
                *[set(prices_hist[s].keys()) for s in valid_symbols]
            )
        )

        if len(common_dates) < 60:
            res = {
                "symbols": valid_symbols,
                "covariance_matrix": [],
                "correlation_matrix": []
            }
            cache_manager.set(cache_key, res, ttl=600)
            return res

        try:
            # price matrix: rows=symbols, cols=dates
            price_matrix = np.array([
                [float(prices_hist[s][d]) for d in common_dates]
                for s in valid_symbols
            ])

            # daily returns
            returns = (
                price_matrix[:, 1:] -
                price_matrix[:, :-1]
            ) / price_matrix[:, :-1]

            returns = np.nan_to_num(returns)

            # annualized covariance
            cov = np.cov(returns, ddof=1) * 252
            corr = np.corrcoef(returns)

            cov = np.nan_to_num(cov)
            corr = np.nan_to_num(corr)

            cov_rounded = [
                [round(float(v), 6) for v in row]
                for row in cov.tolist()
            ]

            corr_rounded = [
                [round(float(v), 4) for v in row]
                for row in corr.tolist()
            ]

        except Exception as e:
            logger.exception("Error calculating covariance matrix: %s", e)
            cov_rounded, corr_rounded = [], []

        res = {
            "symbols": valid_symbols,
            "covariance_matrix": cov_rounded,
            "correlation_matrix": corr_rounded
        }

        cache_manager.set(cache_key, res, ttl=600)
        return res


portfolio_history_service = PortfolioHistoryService()
