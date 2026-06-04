import json
import logging
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from app.models.transaction import Transaction
from app.services.market_data_service import market_data_service

logger = logging.getLogger(__name__)

class PortfolioHistoryService:
    def calculate_historical_performance(self, db: Session, user_id: str) -> List[Dict[str, Any]]:
        """
        Walk chronologically from the earliest transaction date to today.
        Simulate the portfolio holdings on every single day.
        Recompute value and cost basis in-memory using highly-optimized bulk historical price downloads.
        Returns a list of daily observation records.
        """
        try:
            # 1. Fetch all transactions for this user chronologically (ascending)
            transactions = (
                db.query(Transaction)
                .filter(Transaction.user_id == user_id)
                .order_by(Transaction.executed_at.asc())
                .all()
            )
            
            if not transactions:
                return []
                
            # 2. Determine start and end ranges
            start_date = min(t.executed_at for t in transactions)
            start_datetime = datetime.combine(start_date.date(), datetime.min.time())
            end_datetime = datetime.combine(datetime.utcnow().date(), datetime.min.time())
            
            # 3. Fetch bulk historical daily closing prices for all symbols in a single query
            symbols = list(set(t.symbol for t in transactions))
            historical_prices = market_data_service.get_historical_prices_bulk(symbols, start_datetime, end_datetime)
            
            # 4. Chronological holdings forward simulation in-memory
            holdings = {}  # symbol -> {"qty": float, "cost": float}
            last_known_prices = {}
            
            history_records = []
            current_date = start_datetime
            
            while current_date <= end_datetime:
                # Process all transactions executed on this day
                txs_on_date = [t for t in transactions if t.executed_at.date() == current_date.date()]
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
                
                # Calculate total portfolio value and cost on current_date
                total_value = 0.0
                total_cost = 0.0
                date_str = current_date.strftime("%Y-%m-%d")
                active_assets = []
                
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
                    
                    if h["qty"] > 0:
                        active_assets.append({
                            "symbol": symbol,
                            "qty": h["qty"],
                            "value": val,
                            "cost": h["cost"]
                        })
                
                # Compute dynamic risk and diversification metrics in-memory
                diversification_score = 50.0
                risk_score = 5.0
                
                if total_value > 0:
                    # Sector HHI
                    sector_vals = {}
                    for asset in active_assets:
                        sec = market_data_service.get_sector(asset["symbol"])
                        sector_vals[sec] = sector_vals.get(sec, 0.0) + asset["value"]
                        
                    sector_hhi = sum((v / total_value * 100.0) ** 2 for v in sector_vals.values())
                    diversification_score = max(0.0, min(100.0, 100.0 - (sector_hhi / 100.0)))
                    
                    # Asset HHI
                    asset_hhi = sum((a["value"] / total_value * 100.0) ** 2 for a in active_assets)
                    asset_hhi_factor = (asset_hhi / 10000.0) * 4.0
                    sector_hhi_factor = (sector_hhi / 10000.0) * 3.0
                    risk_score = max(1.0, min(10.0, 1.0 + asset_hhi_factor + sector_hhi_factor))
                
                history_records.append({
                    "captured_at": current_date.strftime("%Y-%m-%d"),
                    "total_value": round(total_value, 2),
                    "total_cost": round(total_cost, 2),
                    "risk_score": round(risk_score, 2),
                    "diversification_score": round(diversification_score, 2)
                })
                
                current_date += timedelta(days=1)
                
            return history_records
        except Exception as e:
            logger.error(f"Failed to calculate historical performance for user {user_id}: {e}", exc_info=True)
            raise

    def calculate_portfolio_value_on_date(self, db: Session, user_id: str, target_date: datetime.date) -> Dict[str, Any]:
        """
        Calculate the portfolio total value, total cost, and active positions on a user-specified date
        using all transactions executed on or before that date.
        """
        # Combine date with maximum time to include transactions of that day
        target_datetime = datetime.combine(target_date, datetime.max.time())
        
        # 1. Fetch transactions executed on or before target_datetime
        transactions = (
            db.query(Transaction)
            .filter(Transaction.user_id == user_id, Transaction.executed_at <= target_datetime)
            .order_by(Transaction.executed_at.asc())
            .all()
        )
        
        if not transactions:
            return {
                "date": target_date.strftime("%Y-%m-%d"),
                "total_value": 0.0,
                "total_cost": 0.0,
                "active_positions": []
            }
            
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
                        
        # 3. Fetch prices on target_date in bulk (handles holidays/weekends preceding lookup)
        active_symbols = list(holdings.keys())
        prices = market_data_service.get_prices_on_date_bulk(active_symbols, target_date)
        
        total_value = 0.0
        total_cost = 0.0
        active_positions = []
        
        for symbol, h in holdings.items():
            price = prices.get(symbol)
            if price is None:
                # Fallback to average cost price if no closing price is returned
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
            
        return {
            "date": target_date.strftime("%Y-%m-%d"),
            "total_value": round(total_value, 2),
            "total_cost": round(total_cost, 2),
            "active_positions": active_positions
        }

    def get_historical_summary(self, db: Session, user_id: str) -> Dict[str, Any]:
        """
        Produce a compressed high-intelligence portfolio history summary including:
        - peak_value and its date
        - min_value and its date
        - total_return_percent on cost
        - maximum_drawdown_percent peak-to-trough drop (adjusted for capital flows)
        - sampled_history trend curve containing up to 20 points
        """
        history = self.calculate_historical_performance(db, user_id)
        if not history:
            return {
                "has_history": False,
                "peak_value": 0.0,
                "peak_date": None,
                "min_value": 0.0,
                "min_date": None,
                "current_value": 0.0,
                "total_return_percent": 0.0,
                "maximum_drawdown_percent": 0.0,
                "sampled_history": []
            }
            
        # Peak value
        peak_record = max(history, key=lambda x: x["total_value"])
        
        # Bottom value (exclude initial zeroes if any exist)
        non_zero_history = [x for x in history if x["total_value"] > 0]
        min_record = min(non_zero_history if non_zero_history else history, key=lambda x: x["total_value"])
        
        current_record = history[-1]
        
        # Calculate maximum drawdown based on performance relative to cost basis
        max_dd = 0.0
        peak_return_multiplier = 1.0  # Represents peak growth factor seen so far (value / cost)
        
        for x in history:
            val = x["total_value"]
            cost = x["total_cost"]
            
            if cost > 0:
                # Current growth factor (e.g., 1.15 means a +15% total return)
                current_multiplier = val / cost
                
                # Update the peak performance multiplier seen up to this point
                if current_multiplier > peak_return_multiplier:
                    peak_return_multiplier = current_multiplier
                
                # Calculate drawdown from that peak performance
                dd = ((peak_return_multiplier - current_multiplier) / peak_return_multiplier) * 100.0
                if dd > max_dd:
                    max_dd = dd
                    
        total_cost = current_record["total_cost"]
        total_value = current_record["total_value"]
        total_return_percent = ((total_value - total_cost) / total_cost * 100.0) if total_cost > 0 else 0.0
        
        # Chronological downsampling to 20 data points to avoid prompt bloating
        sampled_history = []
        step = max(1, len(history) // 20)
        for i in range(0, len(history), step):
            rec = history[i]
            sampled_history.append({
                "date": rec["captured_at"],
                "value": round(rec["total_value"], 2),
                "cost": round(rec["total_cost"], 2)
            })
            
        if history[-1]["captured_at"] not in [pt["date"] for pt in sampled_history]:
            sampled_history.append({
                "date": history[-1]["captured_at"],
                "value": round(history[-1]["total_value"], 2),
                "cost": round(history[-1]["total_cost"], 2)
            })
            
        return {
            "has_history": True,
            "peak_value": round(peak_record["total_value"], 2),
            "peak_date": peak_record["captured_at"],
            "min_value": round(min_record["total_value"], 2),
            "min_date": min_record["captured_at"],
            "current_value": round(current_record["total_value"], 2),
            "total_return_percent": round(total_return_percent, 2),
            "maximum_drawdown_percent": round(max_dd, 2),
            "sampled_history": sampled_history
        }

portfolio_history_service = PortfolioHistoryService()
