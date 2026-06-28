import logging
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from app.models.transaction import Transaction
from app.services.market_data_service import market_data_service
from app.schemas.portfolio import HoldingResponse, PortfolioSummaryResponse, PortfolioHoldingsListResponse
from app.core.cache import cache_manager

logger = logging.getLogger(__name__)

class HoldingsService:
    def calculate_holdings(self, db: Session, user_id: str) -> PortfolioHoldingsListResponse:
        try:
            cache_key = f"user_cache:{user_id}:holdings_service"
            cached_data = cache_manager.get(cache_key)
            if cached_data:
                logger.debug(f"[HoldingsService] Cache HIT. Returning cached holdings response for user {user_id}")
                return PortfolioHoldingsListResponse(**cached_data)

            logger.info(f"[HoldingsService] Cache MISS. Starting holdings calculation for user {user_id}")

            # 1. Fetch all transactions for this user, sorted chronologically
            transactions = (
                db.query(Transaction)
                .filter(Transaction.user_id == user_id)
                .order_by(Transaction.executed_at.asc())
                .all()
            )
            
            logger.info(f"[HoldingsService] Loaded {len(transactions)} transactions from database for user {user_id}")
            # fallback sorting if DB index ordering is not applied
            transactions = sorted(transactions, key=lambda x: x.executed_at)

            # 2. Process transactions chronologically to calculate average buy cost and quantity
            # holdings_map: symbol -> {"quantity": float, "average_buy_price": float, "realized_pnl": float}
            holdings_map: Dict[str, Dict[str, Any]] = {}

            for tx in transactions:
                symbol = tx.symbol.upper().strip()
                tx_type = tx.transaction_type.upper().strip()
                qty = float(tx.quantity)
                price = float(tx.price)
                fees = float(tx.fees)

                if symbol not in holdings_map:
                    holdings_map[symbol] = {
                        "quantity": 0.0,
                        "average_buy_price": 0.0,
                        "realized_pnl": 0.0
                    }

                h = holdings_map[symbol]
                current_qty = h["quantity"]
                current_avg = h["average_buy_price"]

                if tx_type == "BUY":
                    new_qty = current_qty + qty
                    # Include fees in total purchase cost (increases average cost basis)
                    new_cost = (current_qty * current_avg) + (qty * price) + fees
                    h["average_buy_price"] = new_cost / new_qty if new_qty > 0 else 0.0
                    h["quantity"] = new_qty
                elif tx_type == "SELL":
                    # Clamp sale quantity to owned quantity to prevent negative holdings
                    sell_qty = min(qty, current_qty)
                    if sell_qty > 0:
                        # Deduct fees from realized gain (reduces realized P&L)
                        realized_gain = sell_qty * (price - current_avg) - fees
                        h["realized_pnl"] += realized_gain
                        h["quantity"] -= sell_qty
                        if h["quantity"] <= 0.0:
                            h["quantity"] = 0.0
                            h["average_buy_price"] = 0.0

            # 3. Separate active positions and gather total realized P&L
            active_holdings = []
            total_realized_pnl = 0.0

            for symbol, h in holdings_map.items():
                total_realized_pnl += h["realized_pnl"]
                if h["quantity"] > 0:
                    active_holdings.append({
                        "symbol": symbol,
                        "quantity": h["quantity"],
                        "average_buy_price": h["average_buy_price"]
                    })

            logger.info(f"[HoldingsService] Computed {len(active_holdings)} active holdings for user {user_id}: {active_holdings}")
            # 4. Fetch live market prices and metadata in bulk for active symbols
            active_symbols = [x["symbol"] for x in active_holdings]
            logger.info(f"[HoldingsService] Requesting market price/metadata bulk lookup for: {active_symbols}")
            metadata_bulk = market_data_service.get_metadata_bulk(active_symbols, db=db)

            # 5. Build individual holding responses
            holdings_responses: List[HoldingResponse] = []
            total_cost = 0.0
            total_value = 0.0

            # First pass to compute total cost and market value
            temp_holdings = []
            for h in active_holdings:
                symbol = h["symbol"]
                qty = h["quantity"]
                avg_buy = h["average_buy_price"]
                mkt_price = metadata_bulk.get(symbol, {}).get("price", avg_buy)  # Fallback to avg_buy if unavailable
                
                mkt_value = qty * mkt_price
                holding_cost = qty * avg_buy
                
                total_cost += holding_cost
                total_value += mkt_value
                
                temp_holdings.append({
                    "symbol": symbol,
                    "quantity": qty,
                    "average_buy_price": avg_buy,
                    "market_price": mkt_price,
                    "market_value": mkt_value,
                    "cost": holding_cost
                })

            # Second pass to compute weights and build responses
            for th in temp_holdings:
                symbol = th["symbol"]
                qty = th["quantity"]
                avg_buy = th["average_buy_price"]
                mkt_price = th["market_price"]
                mkt_value = th["market_value"]
                holding_cost = th["cost"]

                unrealized_pnl = mkt_value - holding_cost
                unrealized_pnl_percent = (unrealized_pnl / holding_cost * 100.0) if holding_cost > 0 else 0.0
                allocation_percent = (mkt_value / total_value * 100.0) if total_value > 0 else 0.0
                company_name = metadata_bulk.get(symbol, {}).get("company_name", symbol)

                holdings_responses.append(
                    HoldingResponse(
                        symbol=symbol,
                        company_name=company_name,
                        quantity=qty,
                        average_buy_price=avg_buy,
                        market_price=mkt_price,
                        market_value=mkt_value,
                        unrealized_pnl=unrealized_pnl,
                        unrealized_pnl_percent=unrealized_pnl_percent,
                        allocation_percent=allocation_percent
                    )
                )

            # Sort holdings by allocation percentage descending
            holdings_responses.sort(key=lambda x: x.allocation_percent, reverse=True)

            # 6. Build summary response
            total_unrealized_pnl = total_value - total_cost
            total_unrealized_pnl_percent = (total_unrealized_pnl / total_cost * 100.0) if total_cost > 0 else 0.0

            summary = PortfolioSummaryResponse(
                total_cost=total_cost,
                total_value=total_value,
                total_unrealized_pnl=total_unrealized_pnl,
                total_unrealized_pnl_percent=total_unrealized_pnl_percent,
                total_realized_pnl=total_realized_pnl
            )

            logger.info(f"[HoldingsService] Completed holdings calculation for user {user_id}. Summary -> Cost: {total_cost:.2f}, Value: {total_value:.2f}, Unrealized P&L: {total_unrealized_pnl:.2f}")
            logger.info(f"Successfully calculated holdings for user {user_id}")

            response_obj = PortfolioHoldingsListResponse(
                holdings=holdings_responses,
                summary=summary
            )
            
            cache_manager.set(cache_key, response_obj.model_dump(), ttl=900)
            return response_obj
        except Exception as e:
            logger.error(f"Failed to calculate holdings for user {user_id}: {e}", exc_info=True)
            raise

holdings_service = HoldingsService()
